from shapely.geometry import Polygon, box


class AreaEvaluator:
    """
    Evaluates whether a normalized bounding box intersects
    with predefined polygon zones (danger, warning, save).

    Zones are prioritized by:
        danger > warning > save
    """

    def __init__(self, areas: dict, overlap_threshold: float = 0.1):
        """
        Parameters
        ----------
        areas : dict
            Format:
            {
                "danger":   [[x1, y1], [x2, y2], ...],
                "warning1": [[...], ...],
                "save1":    [[...], ...]
            }

        overlap_threshold : float
            Minimum overlap ratio (intersection_area / bbox_area)
            required to consider the object inside a zone.
        """
        self.threshold = overlap_threshold
        self.polygons = self._build_polygons(areas)

    # ======================================================
    # Public API
    # ======================================================

    def evaluate(self, bbox_norm):
        """
        Evaluate which zone the object belongs to.

        Parameters
        ----------
        bbox_norm : list[float]
            [x1, y1, x2, y2] normalized (0..1)

        Returns
        -------
        str | None
            Zone name (e.g. "danger", "warning1", "save2")
            or None if not inside any zone.
        """
        obj_box = box(*bbox_norm)
        obj_area = obj_box.area

        if obj_area <= 0:
            return None

        best_zone = None
        best_priority = 999

        for zone_name, poly in self.polygons.items():
            inter_area = poly.intersection(obj_box).area
            ratio = inter_area / obj_area

            if ratio < self.threshold:
                continue

            priority = self._zone_priority(zone_name)

            if priority < best_priority:
                best_zone = zone_name
                best_priority = priority

        return best_zone

    # ======================================================
    # Internal helpers
    # ======================================================

    def _build_polygons(self, areas: dict) -> dict:
        """Convert raw points to shapely Polygons."""
        polygons = {}

        for name, points in areas.items():
            if not points or len(points) < 3:
                continue  # ignore invalid polygons

            try:
                polygons[name] = Polygon(points)
            except Exception:
                # skip broken polygon silently
                continue

        return polygons

    def _zone_priority(self, name: str) -> int:
        """
        Priority rule:
            danger  -> 0
            warning -> 1
            save    -> 2
            other   -> 99
        """
        lname = name.lower()

        if lname.startswith("danger"):
            return 0
        if lname.startswith("warning"):
            return 1
        if lname.startswith("save"):
            return 2

        return 99
