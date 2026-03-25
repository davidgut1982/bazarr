# coding=utf-8

import logging
from flask_restx import Resource, Namespace, fields

from subtitles.mass_operations import mass_batch_operation, VALID_ACTIONS
from ..utils import authenticate

logger = logging.getLogger(__name__)

api_ns_batch = Namespace('Batch', description='Unified batch subtitle operations')


@api_ns_batch.route('subtitles/batch')
class BatchOperation(Resource):
    post_item_model = api_ns_batch.model('BatchItem', {
        'type': fields.String(required=True, description='Type: "episode", "movie", or "series"'),
        'sonarrSeriesId': fields.Integer(description='Sonarr Series ID'),
        'sonarrEpisodeId': fields.Integer(description='Sonarr Episode ID'),
        'radarrId': fields.Integer(description='Radarr Movie ID'),
        'sourceLanguage': fields.String(description='Source language (translate only)'),
        'targetLanguage': fields.String(description='Target language (translate only)'),
        'subtitlePath': fields.String(description='Subtitle path (translate only)'),
        'forced': fields.Boolean(description='Forced subtitle flag'),
        'hi': fields.Boolean(description='Hearing impaired flag'),
    })

    post_options_model = api_ns_batch.model('BatchOptions', {
        'max_offset_seconds': fields.Integer(default=60),
        'no_fix_framerate': fields.Boolean(default=True),
        'gss': fields.Boolean(default=True),
        'force_resync': fields.Boolean(default=False),
    })

    post_request_model = api_ns_batch.model('BatchRequest', {
        'items': fields.List(fields.Nested(post_item_model), required=True),
        'action': fields.String(required=True, description=f'Action: one of {", ".join(sorted(VALID_ACTIONS))}'),
        'options': fields.Nested(post_options_model),
    })

    post_response_model = api_ns_batch.model('BatchResponse', {
        'queued': fields.Integer(description='Number of items processed'),
        'skipped': fields.Integer(description='Number of items skipped'),
        'errors': fields.List(fields.String(), description='Error messages'),
    })

    @authenticate
    @api_ns_batch.doc(body=post_request_model)
    @api_ns_batch.response(200, 'Success', post_response_model)
    @api_ns_batch.response(400, 'Bad Request')
    @api_ns_batch.response(401, 'Not Authenticated')
    def post(self):
        """Execute a batch operation on multiple items"""
        from flask import request
        data = request.get_json()

        if not data:
            return {'error': 'No data provided'}, 400

        action = data.get('action')
        if not action or action not in VALID_ACTIONS:
            return {'error': f'Invalid action. Must be one of: {", ".join(sorted(VALID_ACTIONS))}'}, 400

        items = data.get('items')
        if items is None:
            return {'error': 'No items provided'}, 400

        if not items:
            return {'error': 'Empty items list'}, 400

        options = data.get('options', {})

        result = mass_batch_operation(
            items=items,
            action=action,
            options=options,
            job_id=f'batch_{action}_api',
        )

        if result is None:
            return {'error': 'Batch operation failed'}, 500

        return result, 200
