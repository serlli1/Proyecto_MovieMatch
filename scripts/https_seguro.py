"""Apertura HTTPS verificada con certificados del sistema o de Mozilla.

Nunca desactiva la verificación TLS. Se utiliza para la descarga de TMDB en el ETL.
"""
import ssl
from urllib import error, request

import certifi
import truststore


def _error_de_certificado(excepcion):
    causa = excepcion.reason if isinstance(excepcion, error.URLError) else excepcion
    return (isinstance(causa, ssl.SSLCertVerificationError)
            or "CERTIFICATE_VERIFY_FAILED" in str(causa)
            or "certificate verify failed" in str(causa).lower())


def abrir_https(peticion, timeout=120):
    """Devuelve una respuesta HTTPS verificando cadena y nombre del servidor.

    En Windows, truststore usa CryptoAPI y puede completar certificados
    intermedios que urllib/OpenSSL no consigue encontrar por sí solo.
    """
    contextos = (
        ("Python", None),
        ("certificados del sistema", truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)),
        ("certificados Mozilla", ssl.create_default_context(cafile=certifi.where())),
    )
    ultimo_error = None
    for nombre, contexto in contextos:
        try:
            if contexto is None:
                return request.urlopen(peticion, timeout=timeout)
            return request.urlopen(peticion, timeout=timeout, context=contexto)
        except (error.URLError, ssl.SSLError) as exc:
            if not _error_de_certificado(exc):
                raise
            ultimo_error = exc
            print(f"Aviso: la verificación HTTPS con {nombre} ha fallado.", flush=True)
    raise RuntimeError(
        "No se pudo verificar el certificado HTTPS de "
        f"{peticion.full_url}. Comprueba la fecha y hora del equipo, las "
        "actualizaciones de certificados y si hay un antivirus, VPN o proxy "
        "que inspeccione HTTPS. En ese caso, su certificado raíz debe ser "
        "de confianza para el sistema. No desactives la verificación SSL."
    ) from ultimo_error
