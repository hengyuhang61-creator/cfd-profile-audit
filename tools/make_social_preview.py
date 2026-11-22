"""Generate a GitHub social preview from the actual verified demo SVG.

Optional local tooling: pillow, cairosvg. No dependency is added to CLI.
"""
from io import BytesIO
from pathlib import Path
import sys
from PIL import Image, ImageDraw, ImageFont
import cairosvg

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from cfd_profile_audit.cli import demo_profiles
from cfd_profile_audit.plotting import coverage_svg

ref,comp=demo_profiles()
coverage_svg(ref,comp,ROOT/'docs/coverage-demo.svg')
svg_png=cairosvg.svg2png(url=str(ROOT/'docs/coverage-demo.svg'),output_width=1120)
chart=Image.open(BytesIO(svg_png)).convert('RGB')
canvas=Image.new('RGB',(1280,640),'#0f172a')
draw=ImageDraw.Draw(canvas)
try:
    title_font=ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf',46)
    subtitle_font=ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',22)
except OSError:
    title_font=ImageFont.load_default();subtitle_font=title_font
draw.text((80,29),'cfd-profile-audit',font=title_font,fill='#f8fafc')
draw.text((80,90),'Know what your CFD error score actually covers.',font=subtitle_font,fill='#93c5fd')
canvas.paste(chart,(80,143))
draw.text((80,605),'RMSE = 0 does not imply full support  |  13 / 21 points  |  full-domain FAIL',font=subtitle_font,fill='#fdba74')
canvas.save(ROOT/'assets/social-preview.png')
