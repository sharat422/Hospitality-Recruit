import qrcode
import io
import random
import string
import base64
import logging

logger = logging.getLogger(__name__)


def generate_short_code(length=8) -> str:
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=length))


def generate_qr_image_base64(url: str) -> str:
    """Generate QR code PNG and return as base64 data URI."""
    qr = qrcode.QRCode(version=1, box_size=10, border=4)
    qr.add_data(url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    b64 = base64.b64encode(buf.getvalue()).decode()
    return f"data:image/png;base64,{b64}"
