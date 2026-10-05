"""Complete the published Sachplan Militär XTF with the geometries of the same dataset's GDB export.

The XTF (SPM_V1_4_In_Kraft_LV95.xtf) carries every object and attribute but empty Point/Surface structures;
the GDB carries the geometries, keyed by the same TID (XTF_ID). Only geometry is added; nothing else changes.
"""

import csv
import re
import sys
import xml.etree.ElementTree as ET

NS = "http://www.interlis.ch/INTERLIS2.3"
Q = lambda tag: f"{{{NS}}}{tag}"  # noqa: E731
csv.field_size_limit(10**9)

src_xtf, fac_csv, pm_csv, out_xtf = sys.argv[1:5]


def fmt(v: float) -> str:
    return f"{v:.3f}"


def coord(parent, x, y):
    c = ET.SubElement(parent, Q("COORD"))
    ET.SubElement(c, Q("C1")).text = fmt(x)
    ET.SubElement(c, Q("C2")).text = fmt(y)


def polygons(wkt: str):
    """MULTIPOLYGON (((x y, ...), (hole)), ...) -> [[ring, ...], ...] of (x, y) lists."""
    body = wkt[wkt.index("(") :]
    result = []
    for poly in re.findall(r"\(\((.*?)\)\)", body.replace(" ((", "((")):
        rings = []
        for ring in poly.split("),("):
            rings.append([tuple(map(float, p.split())) for p in ring.replace("(", "").replace(")", "").split(",")])
        result.append(rings)
    return result


def circle_centre(wkt: str):
    pts = [tuple(map(float, p.split())) for p in re.findall(r"([\d.]+ [\d.]+)", wkt)]
    return (pts[0][0] + pts[2][0]) / 2, (pts[0][1] + pts[2][1]) / 2


facilities = {r["XTF_ID"]: tuple(map(float, re.findall(r"[\d.]+", r["Shape"]))) for r in csv.DictReader(open(fac_csv))}
measures = {r["XTF_ID"]: r["Shape"] for r in csv.DictReader(open(pm_csv))}

ET.register_namespace("", NS)
tree = ET.parse(src_xtf)
root = tree.getroot()
header = root.find(Q("HEADERSECTION"))
comment = ET.SubElement(header, Q("COMMENT"))
comment.text = (
    "Geometries completed from the File Geodatabase export of the same dataset "
    "(sachplan-infrastruktur-militaer_kraft_2056.gdb.zip), matched by TID (XTF_ID); the published XTF carries "
    "empty geometry structures. Attributes and TIDs unchanged. Consecutive repeated vertices of the GDB are "
    "removed; the GDB draws the point-modelled measures (32-M-1) as 25 m circles, written here as their centre."
)

stats = {"facility_points": 0, "measure_points": 0, "measure_surfaces": 0, "missing": []}
for basket in root.find(Q("DATASECTION")):
    for obj in basket:
        tid = obj.get("TID")
        cls = obj.tag.rsplit(".", 1)[-1]
        point = obj.find(Q("Point"))
        surface = obj.find(Q("Surface"))
        if cls == "Facility_SPM" and point is not None:
            xy = facilities.get(tid)
            if xy is None:
                stats["missing"].append(tid)
                continue
            ps = point.find(f".//{Q('BaseModel_SectoralPlans_LV95_V1_4.PointStructure')}")
            coord(ET.SubElement(ps, Q("Point")), *xy)
            stats["facility_points"] += 1
        elif cls == "PlanningMeasure":
            wkt = measures.get(tid)
            if wkt is None:
                stats["missing"].append(tid)
                continue
            if point is not None:
                # The GDB draws these as 25 m circles centred exactly on the point the model declares.
                ps = point.find(f".//{Q('BaseModel_SectoralPlans_LV95_V1_4.PointStructure')}")
                coord(ET.SubElement(ps, Q("Point")), *circle_centre(wkt))
                stats["measure_points"] += 1
            elif surface is not None:
                surfaces = surface.find(f".//{Q('Surfaces')}")
                for child in list(surfaces):
                    surfaces.remove(child)
                for rings in polygons(wkt):
                    ss = ET.SubElement(surfaces, Q("GeometryCHLV95_V1.SurfaceStructure"))
                    surf = ET.SubElement(ET.SubElement(ss, Q("Surface")), Q("SURFACE"))
                    for ring in rings:
                        poly = ET.SubElement(ET.SubElement(surf, Q("BOUNDARY")), Q("POLYLINE"))
                        # The GDB repeats some vertices: a zero-length segment has no shape and is not valid INTERLIS.
                        rounded = [(fmt(x), fmt(y)) for x, y in ring]
                        kept = [p for i, p in enumerate(ring) if i == 0 or rounded[i] != rounded[i - 1]]
                        for x, y in kept:
                            coord(poly, x, y)
                stats["measure_surfaces"] += 1

tree.write(out_xtf, encoding="UTF-8", xml_declaration=True)
print(stats["facility_points"], "facility points,", stats["measure_points"], "measure points,",
      stats["measure_surfaces"], "measure surfaces, missing:", stats["missing"][:5], len(stats["missing"]))
