from django.apps import AppConfig


class TourApiConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "tour_api"

    def ready(self):
        import sys, os
        from pathlib import Path
        repo_root = str(Path(__file__).resolve().parent.parent.parent)
        if repo_root not in sys.path:
            sys.path.insert(0, repo_root)
        try:
            from api.korea_airports_flight_client import _preload_odcloud_snapshot
            _preload_odcloud_snapshot()
        except Exception:
            pass
