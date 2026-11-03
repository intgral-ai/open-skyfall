from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


def draw_reference(path):
    image = Image.new("RGB", (1200, 1000), "#fafaf7")
    draw = ImageDraw.Draw(image)
    title = ImageFont.load_default(size=32)
    font = ImageFont.load_default(size=22)
    small = ImageFont.load_default(size=18)
    ink, accent = "#303b3b", "#b7c6bc"

    def label(xy, text, size=font):
        draw.text(xy, text, fill=ink, font=size)

    def dimension(start, end, text, vertical=False):
        draw.line([start, end], fill=ink, width=2)
        for x, y in [start, end]:
            if vertical:
                draw.line([(x - 7, y), (x + 7, y)], fill=ink, width=2)
            else:
                draw.line([(x, y - 7), (x, y + 7)], fill=ink, width=2)
        x, y = (start[0] + end[0]) / 2, (start[1] + end[1]) / 2
        if vertical:
            label((x - 52, y - 10), text, small)
        else:
            label((x - len(text) * 5, y - 28), text, small)

    label((60, 35), "Workshop side table", title)
    label((60, 82), "Reference drawing. All dimensions in mm. Orthographic views.", small)
    label((145, 140), "FRONT", small)
    draw.rectangle((145, 215, 545, 235), fill=accent, outline=ink, width=3)
    draw.rectangle((160, 235, 190, 665), fill="#d9dfd7", outline=ink, width=3)
    draw.rectangle((500, 235, 530, 665), fill="#d9dfd7", outline=ink, width=3)
    dimension((145, 185), (545, 185), "400")
    draw.line([(145, 195), (145, 215)], fill=ink)
    draw.line([(545, 195), (545, 215)], fill=ink)
    dimension((98, 215), (98, 665), "450", vertical=True)
    dimension((585, 235), (585, 665), "430", vertical=True)
    draw.line([(545, 225), (595, 205)], fill=ink, width=2)
    label((560, 175), "Top thickness 20", small)
    dimension((160, 705), (190, 705), "30")
    label((145, 748), "The back pair overlaps in this front projection.", small)

    label((735, 140), "TOP", small)
    draw.rectangle((735, 215, 1135, 515), fill="#e6ece6", outline=ink, width=3)
    for x, y in [(765, 245), (1105, 245), (765, 485), (1105, 485)]:
        draw.rectangle((x - 15, y - 15, x + 15, y + 15), fill=accent, outline=ink, width=2)
        draw.line([(x - 22, y), (x + 22, y)], fill=ink, width=1)
        draw.line([(x, y - 22), (x, y + 22)], fill=ink, width=1)
    dimension((735, 185), (1135, 185), "400")
    dimension((1170, 215), (1170, 515), "300", vertical=True)
    draw.line([(935, 205), (935, 535)], fill="#b0b7b0", width=1)
    draw.line([(720, 365), (1145, 365)], fill="#b0b7b0", width=1)
    label((740, 555), "Four square legs, 30 x 30 x 430.", small)
    label((740, 590), "Leg centers from the table center", small)
    label((740, 620), "X = -170 or +170", small)
    label((740, 650), "Y = -120 or +120", small)
    label((740, 690), "Top = 400 x 300 x 20.", small)

    draw.line([(60, 820), (1140, 820)], fill="#c6cdc6", width=2)
    label((60, 850), "Part boundaries shown: one top and four separate legs.", font)
    label((60, 890), "Connections, fasteners and material are unspecified. Do not invent hidden hardware.", small)
    label((60, 935), "Original reference illustration. Distributed under the repository MIT license.", small)
    image.save(path)


if __name__ == "__main__":
    draw_reference(Path(__file__).with_name("reference.png"))
