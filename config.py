import os
from dotenv import load_dotenv

load_dotenv()

# Check if we are running inside Docker
IS_DOCKER = os.path.exists('/.dockerenv')

if IS_DOCKER:
    FONT_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
else:
    # Your local Ubuntu path
    FONT_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"




# Hardware & Performance
# Set to True only if you have VA-API (Intel/AMD) drivers configured on Ubuntu
USE_GPU = os.getenv("USE_GPU", "False").lower() == "true"
VIDEO_ENCODER = "h264_vaapi" if USE_GPU else "libx264"
THREADS = "4" # X270 has 4 threads

# Dimensions (Vertical 9:16)
WIDTH = 1080
HEIGHT = 1920

# Paths
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEMP_DIR = os.path.join(BASE_DIR, "temp")
ASSETS_DIR = os.path.join(BASE_DIR, "assets")
# Ensure these exist
os.makedirs(TEMP_DIR, exist_ok=True)

# Assets (Update these to your actual font/gameplay paths)
FONT_PATH = os.path.join(ASSETS_DIR, "fonts", "bold_font.ttf")
# Point this to a local gameplay file or a specific source
GAMEPLAY_SOURCE = os.getenv("GAMEPLAY_PATH", "assets/gameplay.mp4")

