# coding=utf-8

import logging
from flask_restx import Resource, Namespace, fields

from subtitles.mass_sync import mass_sync_subtitles
from ..utils import authenticate

logger = logging.getLogger(__name__)

api_ns_batch_sync = Namespace('BatchSync', description='Batch sync subtitles')


@api_ns_batch_sync.route('subtitles/sync/batch')
class BatchSync(Resource):
    post_item_model = api_ns_batch_sync.model('BatchSyncItem', {
        'type': fields.String(required=True, description='Type: "episode", "movie", or "series"'),
        'sonarrSeriesId': fields.Integer(description='Sonarr Series ID'),
        'sonarrEpisodeId': fields.Integer(description='Sonarr Episode ID'),
        'radarrId': fields.Integer(description='Radarr Movie ID'),
    })

    post_options_model = api_ns_batch_sync.model('BatchSyncOptions', {
        'max_offset_seconds': fields.Integer(default=60, description='Maximum offset in seconds'),
        'no_fix_framerate': fields.Boolean(default=True, description='Skip framerate correction'),
        'gss': fields.Boolean(default=True, description='Use Golden-Section Search'),
        'force_resync': fields.Boolean(default=False, description='Re-sync already synced subtitles'),
    })

    post_request_model = api_ns_batch_sync.model('BatchSyncRequest', {
        'items': fields.List(fields.Nested(post_item_model), required=True),
        'options': fields.Nested(post_options_model),
    })

    post_response_model = api_ns_batch_sync.model('BatchSyncResponse', {
        'queued': fields.Integer(description='Number of sync jobs queued'),
        'skipped': fields.Integer(description='Number of subtitles skipped'),
        'errors': fields.List(fields.String(), description='Error messages'),
    })

    @authenticate
    @api_ns_batch_sync.doc(body=post_request_model)
    @api_ns_batch_sync.response(200, 'Success', post_response_model)
    @api_ns_batch_sync.response(400, 'Bad Request')
    @api_ns_batch_sync.response(401, 'Not Authenticated')
    def post(self):
        """Queue batch sync jobs for multiple items"""
        from flask import request
        data = request.get_json()

        if not data or 'items' not in data:
            return {'error': 'No items provided'}, 400

        items = data.get('items', [])
        if not items:
            return {'error': 'Empty items list'}, 400

        options = data.get('options', {})

        result = mass_sync_subtitles(items=items, options=options, job_id='batch_sync_api')
        if result is None:
            return {'error': 'Mass sync failed'}, 500

        return result, 200
