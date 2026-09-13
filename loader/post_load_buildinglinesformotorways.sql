-- Convenience view for pygeoapi: GeoJSON (RFC 7946, what pygeoapi ultimately
-- emits) has no CircularString/CompoundCurve - ST_CurveToLine linearizes any
-- curved geometry to a plain LineString so the live map never errors on
-- ST_AsGeoJSON. The true curve stays in buildingline.geometry itself.
CREATE OR REPLACE VIEW buildingline_geo AS
SELECT
    id,
    ST_CurveToLine(geometry) AS geom,
    status,
    approvaldate,
    approvingauthority,
    planningapprovalname,
    publicationdatefrom,
    publicationdateto,
    weblink
FROM buildingline;
