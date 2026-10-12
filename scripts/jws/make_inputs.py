"""Generate our own JWW inputs for Jw_cad's JWS registration oracle."""
import argparse
from pathlib import Path
import ezjww


def cases():
    out = {}
    for name in ('basic', 'scales', 'geometry', 'unicode', 'blocks', 'image'):
        d = ezjww.new()
        m = d.modelspace()
        m.add_line((10, 20), (40, 20))
        m.add_line((10, 20), (10, 40))
        if name == 'basic':
            m.add_circle((30, 30), 5)
        elif name == 'scales':
            d.options['layer_groups'][0]['scale'] = 50
            d.options['layer_groups'][1]['scale'] = 100
            m.add_line((-40, -20), (-20, -20), jwwattribs={'layer_group': 1})
        elif name == 'geometry':
            m.add_circle((-40, 30), 8)
            m.add_arc((-10, 30), 8, 30, 210)
            m.add_ellipse((-40, 0), 8, 0.5, tilt_angle=30)
            m.add_point((-10, 0))
            m.add_solid((-40, -30), (-20, -30), (-30, -15))
            m.add_circle_solid((10, -20), 6)
            m.add_dimension((30, -30), (60, -30), '30', (38, -26))
        elif name == 'unicode':
            m.add_text('日本語𠮷ｶﾅ ABC', (-50, -20), font_name='ＭＳ ゴシック')
            m.add_text('縦書き', (-50, 0), angle=90)
        elif name == 'blocks':
            unit = ezjww.new().modelspace()
            unit.add_line((0, 0), (10, 0))
            unit.add_circle((5, 5), 3)
            d.add_block('部品𠮷', unit.entities)
            unit.entities = []
            ref = unit.add_block_ref(0, (0, 0), rotation=30)
            d.add_block('入れ子', [ref])
            m.add_block_ref('入れ子', (-40, -20), rotation=45)
            m.add_block_ref('部品𠮷', (30, -20), scale_x=2, scale_y=0.5)
        elif name == 'image':
            # 2x2 uncompressed 24-bit BMP, generated independently of the JWW writer.
            import struct
            pixels = bytes((0, 0, 255, 0, 255, 0, 0, 0, 255, 0, 0, 255, 255, 255, 0, 0))
            bmp = b'BM' + struct.pack('<IHHI', 54 + len(pixels), 0, 0, 54) + struct.pack('<IiiHHIIiiII', 40, 2, 2, 1, 24, 0, len(pixels), 2835, 2835, 0, 0) + pixels
            d.embed_image('symbol.bmp', bmp)
            m.add_image('symbol.bmp', (-30, -20), 20, 10)
        out[name] = d
    return out


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('output', type=Path)
    root = p.parse_args().output
    root.mkdir(parents=True, exist_ok=True)
    for name, doc in cases().items():
        path = root / (name + '.jww')
        if path.exists():
            raise FileExistsError(path)
        doc.saveas(path)
        print(path)


if __name__ == '__main__':
    main()
