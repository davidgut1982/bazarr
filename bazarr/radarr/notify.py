# coding=utf-8

import logging
import requests

from app.config import settings, get_ssl_verify
from radarr.info import radarr_headers, url_api_radarr


def notify_radarr(radarr_id):
    try:
        url = f"{url_api_radarr()}command"
        data = {
            'name': 'RescanMovie',
            'movieId': int(radarr_id)
        }
        requests.post(url, json=data, timeout=int(settings.radarr.http_timeout), verify=get_ssl_verify('radarr'),
                      headers=radarr_headers(settings.radarr.apikey))
    except Exception:
        logging.exception('BAZARR cannot notify Radarr')
