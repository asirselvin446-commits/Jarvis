from PIL import Image, ImageDraw, ImageFont
import os

def create_tray_icon():
    # Create a 64x64 transparent image
    size = 64
    image = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    
    # Draw a circle with the primary-fixed-dim color from Aether UI (#00dbe7)
    draw.ellipse((4, 4, size-4, size-4), fill="#050505", outline="#00dbe7", width=3)
    
    # Try to use a default font, or fallback to default
    try:
        font = ImageFont.truetype("arial.ttf", 36)
    except:
        font = ImageFont.load_default()
        
    # Draw 'J' in the center
    # get text bounding box
    bbox = draw.textbbox((0, 0), "J", font=font)
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]
    
    x = (size - text_w) / 2
    y = (size - text_h) / 2 - 4  # slight vertical adjustment
    
    draw.text((x, y), "J", font=font, fill="#00dbe7")
    
    # Save it to the assets folder if it exists, otherwise current dir
    assets_dir = os.path.join(os.path.dirname(__file__), 'assets')
    if not os.path.exists(assets_dir):
        os.makedirs(assets_dir)
        
    icon_path = os.path.join(assets_dir, 'tray_icon.png')
    image.save(icon_path)
    print(f"Icon generated at {icon_path}")

if __name__ == "__main__":
    create_tray_icon()
