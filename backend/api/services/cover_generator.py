from PIL import Image, ImageDraw, ImageFont
from pathlib import Path
import logging

logger = logging.getLogger(__name__)

class CoverArtGenerator:
    def __init__(self, assets_dir: Path):
        self.assets_dir = assets_dir
        self.base_image_path = assets_dir / "listenbrainz_cover_base.png"
        
        # Ensure assets dir exists
        if not self.assets_dir.exists():
            self.assets_dir.mkdir(parents=True, exist_ok=True)

    def generate_cover(self, title: str, subtitle: str = "") -> bytes:
        """
        Generates a cover image with title overlay.
        Returns bytes of the JPEG image.
        """
        try:
            if not self.base_image_path.exists():
                logger.error(f"Base image not found at {self.base_image_path}")
                return None

            # Open base image
            with Image.open(self.base_image_path) as img:
                img = img.convert("RGB")
                draw = ImageDraw.Draw(img)
                width, height = img.size

                # Dynamic font size calculation (naive but functional)
                # Aim for title to be ~80% of width
                title_font_size = int(width / 8)
                subtitle_font_size = int(width / 15)
                
                # Load default font (Pillow native) or custom if available
                # Note: System fonts path varies. For now using default PIL font which is very small/ugly.
                # BETTER: Load a specific TTF if we add one.
                # For robust "default", we can try to find a system font or just use default.
                # Let's try to load a nice font if possible, else failover.
                font_path = self.assets_dir / "font.ttf"
                if font_path.exists():
                    font = ImageFont.truetype(str(font_path), title_font_size)
                    sub_font = ImageFont.truetype(str(font_path), subtitle_font_size)
                else:
                    # Fallback to default (ugly but works)
                    logger.warning("Custom font not found, using default.")
                    font = ImageFont.load_default() 
                    # Scale default font? Not easily possible with load_default().
                    # Actually, we can use a system font path commonly found on linux containers.
                    try:
                        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", title_font_size)
                        sub_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", subtitle_font_size)
                    except:
                         font = ImageFont.load_default()
                         sub_font = ImageFont.load_default()

                # Calculate text position (Centered)
                # Pillow 10+ uses textbbox
                try:
                    left, top, right, bottom = draw.textbbox((0, 0), title, font=font)
                    text_width = right - left
                    text_height = bottom - top
                except AttributeError:
                    # Older Pillow
                    text_width, text_height = draw.textsize(title, font=font)

                x = (width - text_width) / 2
                y = (height - text_height) / 2

                # Apply a slight shadow for readability
                shadow_offset = 5
                draw.text((x + shadow_offset, y + shadow_offset), title, font=font, fill=(0, 0, 0))
                draw.text((x, y), title, font=font, fill=(255, 255, 255))
                
                # Subtitle (User initials or full name)
                if subtitle:
                    try:
                        sl, st, sr, sb = draw.textbbox((0, 0), subtitle, font=sub_font)
                        sub_w = sr - sl
                        sub_h = sb - st
                    except:
                        sub_w, sub_h = draw.textsize(subtitle, font=sub_font)
                        
                    sx = (width - sub_w) / 2
                    sy = y + text_height + 20
                    
                    draw.text((sx+2, sy+2), subtitle, font=sub_font, fill=(0,0,0))
                    draw.text((sx, sy), subtitle, font=sub_font, fill=(200, 200, 200))

                # Save to bytes
                from io import BytesIO
                out_buffer = BytesIO()
                img.save(out_buffer, format="JPEG", quality=90)
                return out_buffer.getvalue()

        except Exception as e:
            logger.error(f"Failed to generate cover: {e}")
            return None
