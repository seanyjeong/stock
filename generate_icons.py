#!/usr/bin/env python3
"""Generate app icons for Daily Stock Story PWA."""

from PIL import Image, ImageDraw, ImageFont
import os

def create_stock_icon(size: int, output_path: str):
    """Create a stock chart icon with the given size."""
    # Dark background matching theme
    bg_color = (13, 17, 23)  # #0d1117

    # Create image
    img = Image.new('RGBA', (size, size), bg_color)
    draw = ImageDraw.Draw(img)

    # Padding
    padding = size // 8
    chart_width = size - (padding * 2)
    chart_height = size - (padding * 2)

    # Chart area
    chart_left = padding
    chart_bottom = size - padding
    chart_top = padding

    # Draw candlestick-like bars (simplified stock chart)
    num_bars = 5
    bar_width = chart_width // (num_bars * 2)
    gap = bar_width

    # Stock data simulation (going up trend)
    bars = [
        (0.6, 0.4, 0.65, 0.35),  # (open, close, high, low) as ratios
        (0.5, 0.35, 0.55, 0.3),
        (0.55, 0.4, 0.6, 0.35),
        (0.4, 0.25, 0.45, 0.2),
        (0.3, 0.15, 0.35, 0.1),  # Latest - big green candle
    ]

    for i, (open_r, close_r, high_r, low_r) in enumerate(bars):
        x = chart_left + (i * (bar_width + gap)) + gap // 2

        # Convert ratios to Y positions (inverted - lower ratio = higher position)
        open_y = chart_top + int(open_r * chart_height)
        close_y = chart_top + int(close_r * chart_height)
        high_y = chart_top + int(high_r * chart_height)
        low_y = chart_top + int(low_r * chart_height)

        # Determine if bullish (green) or bearish (red)
        is_bullish = close_r < open_r  # Lower close ratio = higher price = bullish
        color = (34, 197, 94) if is_bullish else (239, 68, 68)  # green-500 / red-500

        # Draw wick (high-low line)
        wick_x = x + bar_width // 2
        draw.line([(wick_x, high_y), (wick_x, low_y)], fill=color, width=max(2, size // 64))

        # Draw body (open-close rectangle)
        body_top = min(open_y, close_y)
        body_bottom = max(open_y, close_y)
        draw.rectangle(
            [(x, body_top), (x + bar_width, body_bottom)],
            fill=color,
            outline=color
        )

    # Draw upward trend line
    trend_color = (34, 197, 94, 180)  # Green with alpha
    line_points = [
        (chart_left, chart_bottom - chart_height * 0.3),
        (chart_left + chart_width * 0.3, chart_bottom - chart_height * 0.4),
        (chart_left + chart_width * 0.5, chart_bottom - chart_height * 0.5),
        (chart_left + chart_width * 0.7, chart_bottom - chart_height * 0.65),
        (chart_left + chart_width, chart_bottom - chart_height * 0.85),
    ]

    for i in range(len(line_points) - 1):
        draw.line(
            [line_points[i], line_points[i + 1]],
            fill=(34, 197, 94),
            width=max(3, size // 40)
        )

    # Add a subtle "S" watermark for Stock
    try:
        font_size = size // 4
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", font_size)
    except:
        font = ImageFont.load_default()

    # Draw "S" in bottom right corner with low opacity
    text_color = (255, 255, 255, 60)
    text_x = size - padding - font_size // 2
    text_y = size - padding - font_size

    # Create text overlay
    text_img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    text_draw = ImageDraw.Draw(text_img)
    text_draw.text((text_x, text_y), "$", font=font, fill=text_color)

    # Composite
    img = Image.alpha_composite(img, text_img)

    # Save
    img.save(output_path, 'PNG')
    print(f"Created: {output_path} ({size}x{size})")


def create_svg_icon(output_path: str):
    """Create an SVG version of the icon."""
    svg_content = '''<svg xmlns="http://www.w3.org/2000/svg" width="512" height="512" viewBox="0 0 512 512">
  <title>Daily Stock Story</title>
  <!-- Background -->
  <rect width="512" height="512" fill="#0d1117"/>

  <!-- Candlestick chart -->
  <g stroke-width="8">
    <!-- Bar 1 - Red (bearish) -->
    <line x1="90" y1="180" x2="90" y2="280" stroke="#ef4444"/>
    <rect x="70" y="200" width="40" height="60" fill="#ef4444"/>

    <!-- Bar 2 - Green (bullish) -->
    <line x1="170" y1="150" x2="170" y2="260" stroke="#22c55e"/>
    <rect x="150" y="170" width="40" height="70" fill="#22c55e"/>

    <!-- Bar 3 - Red (bearish) -->
    <line x1="250" y1="160" x2="250" y2="250" stroke="#ef4444"/>
    <rect x="230" y="180" width="40" height="50" fill="#ef4444"/>

    <!-- Bar 4 - Green (bullish) -->
    <line x1="330" y1="100" x2="330" y2="220" stroke="#22c55e"/>
    <rect x="310" y="120" width="40" height="80" fill="#22c55e"/>

    <!-- Bar 5 - Big Green (bullish) -->
    <line x1="410" y1="60" x2="410" y2="180" stroke="#22c55e"/>
    <rect x="390" y="80" width="40" height="80" fill="#22c55e"/>
  </g>

  <!-- Trend line -->
  <polyline
    points="64,320 150,280 250,240 350,160 448,80"
    fill="none"
    stroke="#22c55e"
    stroke-width="6"
    stroke-linecap="round"
    stroke-opacity="0.8"
  />

  <!-- Dollar sign watermark -->
  <text x="420" y="450" font-family="Arial, sans-serif" font-size="120" font-weight="bold" fill="rgba(255,255,255,0.15)">$</text>
</svg>'''

    with open(output_path, 'w') as f:
        f.write(svg_content)
    print(f"Created: {output_path}")


def main():
    # Output directory
    static_dir = os.path.join(os.path.dirname(__file__), 'web', 'static')
    assets_dir = os.path.join(os.path.dirname(__file__), 'web', 'src', 'lib', 'assets')

    os.makedirs(static_dir, exist_ok=True)
    os.makedirs(assets_dir, exist_ok=True)

    # Generate PNG icons
    create_stock_icon(192, os.path.join(static_dir, 'icon-192.png'))
    create_stock_icon(512, os.path.join(static_dir, 'icon-512.png'))

    # Generate SVG favicon
    create_svg_icon(os.path.join(static_dir, 'favicon.svg'))
    create_svg_icon(os.path.join(assets_dir, 'favicon.svg'))

    print("\nDone! Update manifest.json to include the new icons.")


if __name__ == '__main__':
    main()
