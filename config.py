"""Shared settings: paths, video dimensions, encoder choice. Imported by main.py and the modules."""
import os
from dotenv import load_dotenv

load_dotenv()


# DejaVu Bold is installed by the Dockerfile and the CI workflow (fonts-dejavu-core) and is
# present on stock Ubuntu, so the same path works in Docker and locally. Override with FONT_PATH.
FONT_PATH = os.getenv("FONT_PATH", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf")




# Hardware & Performance
# Set to True only if you have VA-API (Intel/AMD) drivers configured on Ubuntu
USE_GPU = os.getenv("USE_GPU", "False").lower() == "true"
VIDEO_ENCODER = "h264_vaapi" if USE_GPU else "libx264"
THREADS = "4" 

# Dimensions (Vertical 9:16)
WIDTH = 1080
HEIGHT = 1920

# Paths
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEMP_DIR = os.path.join(BASE_DIR, "temp")
ASSETS_DIR = os.path.join(BASE_DIR, "assets")
# Ensure these exist
os.makedirs(TEMP_DIR, exist_ok=True)
