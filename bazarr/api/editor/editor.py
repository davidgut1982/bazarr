# coding=utf-8

import json
import logging
import os
import struct
import subprocess

from flask import Response, request, send_file
from flask_restx import Namespace, Resource

from app.database import TableEpisodes, TableMovies, database, select
from app.get_args import args
from utilities.path_mappings import path_mappings

from ..utils import authenticate

logger = logging.getLogger(__name__)

api_ns_editor = Namespace('Editor', description='Video editor streaming and metadata')

PEAKS_CACHE_DIR = os.path.join(args.config_dir, 'cache', 'peaks')


def _resolve_video_path(media_type, media_id):
    """Look up the video file path from the database and apply path mappings.

    Returns the mapped file path on success, or a (message, status_code) tuple on failure.
    """
    if media_type == 'episode':
        row = database.execute(
            select(TableEpisodes.path)
            .where(TableEpisodes.sonarrEpisodeId == media_id)
        ).first()
        if not row:
            return 'Episode not found', 404
        return path_mappings.path_replace(row.path)

    elif media_type == 'movie':
        row = database.execute(
            select(TableMovies.path)
            .where(TableMovies.radarrId == media_id)
        ).first()
        if not row:
            return 'Movie not found', 404
        return path_mappings.path_replace_movie(row.path)

    return 'Invalid media type, must be "episode" or "movie"', 400


def _get_ffmpeg():
    """Return the path to the ffmpeg binary."""
    from utilities.binaries import get_binary
    return get_binary("ffmpeg")


def _get_ffprobe():
    """Return the path to the ffprobe binary."""
    from utilities.binaries import get_binary
    return get_binary("ffprobe")


def _probe_video(video_path):
    """Run ffprobe and return parsed JSON metadata for the file."""
    ffprobe = _get_ffprobe()
    cmd = [
        ffprobe,
        '-v', 'quiet',
        '-print_format', 'json',
        '-show_format',
        '-show_streams',
        video_path,
    ]
    result = subprocess.run(cmd, capture_output=True, timeout=30)
    if result.returncode != 0:
        logger.error('ffprobe failed for %s: %s', video_path, result.stderr.decode(errors='replace'))
        return None
    return json.loads(result.stdout)


def _can_direct_play(video_path, probe_data=None):
    """Check if the video can be served directly to the browser (h264 in mp4/m4v container)."""
    ext = os.path.splitext(video_path)[1].lower()
    if ext not in ('.mp4', '.m4v'):
        return False

    if probe_data is None:
        probe_data = _probe_video(video_path)
    if not probe_data:
        return False

    for stream in probe_data.get('streams', []):
        if stream.get('codec_type') == 'video':
            codec = stream.get('codec_name', '').lower()
            if codec in ('h264', 'avc'):
                return True
    return False


def _parse_range_header(range_header, file_size):
    """Parse an HTTP Range header. Returns (start, end) or None."""
    if not range_header or not range_header.startswith('bytes='):
        return None
    try:
        range_spec = range_header[6:]
        start_str, end_str = range_spec.split('-', 1)
        start = int(start_str) if start_str else 0
        end = int(end_str) if end_str else file_size - 1
        if start < 0 or start >= file_size or end >= file_size or start > end:
            return None
        return start, end
    except (ValueError, IndexError):
        return None


def _serve_file_with_ranges(file_path, mimetype):
    """Serve a file with HTTP Range request support."""
    file_size = os.path.getsize(file_path)
    range_header = request.headers.get('Range')
    range_tuple = _parse_range_header(range_header, file_size)

    if range_tuple:
        start, end = range_tuple
        length = end - start + 1

        def generate():
            with open(file_path, 'rb') as f:
                f.seek(start)
                remaining = length
                while remaining > 0:
                    chunk_size = min(64 * 1024, remaining)
                    data = f.read(chunk_size)
                    if not data:
                        break
                    remaining -= len(data)
                    yield data

        response = Response(
            generate(),
            status=206,
            mimetype=mimetype,
            direct_passthrough=True,
        )
        response.headers['Content-Range'] = f'bytes {start}-{end}/{file_size}'
        response.headers['Content-Length'] = length
        response.headers['Accept-Ranges'] = 'bytes'
        return response

    response = send_file(file_path, mimetype=mimetype)
    response.headers['Accept-Ranges'] = 'bytes'
    return response


def _stream_ffmpeg(cmd, mimetype):
    """Run an ffmpeg command and stream its stdout as a Flask Response."""
    def generate():
        process = None
        try:
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
            )
            while True:
                chunk = process.stdout.read(64 * 1024)
                if not chunk:
                    break
                yield chunk
            process.wait()
            if process.returncode != 0:
                logger.error('ffmpeg exited with code %d for cmd: %s', process.returncode, ' '.join(cmd[:5]))
        except Exception:
            logger.exception('Error during ffmpeg streaming')
        finally:
            if process and process.poll() is None:
                process.kill()
                process.wait()

    return Response(
        generate(),
        mimetype=mimetype,
        headers={
            'Cache-Control': 'no-cache',
            'Accept-Ranges': 'none',
        },
    )


def _validate_params():
    """Extract and validate mediaType and mediaId from query parameters.

    Returns (media_type, media_id) on success, or a (message, status_code) tuple on failure.
    """
    media_type = request.args.get('mediaType')
    media_id = request.args.get('mediaId')

    if not media_type or media_type not in ('episode', 'movie'):
        return 'mediaType must be "episode" or "movie"', 400
    if not media_id:
        return 'mediaId is required', 400
    try:
        media_id = int(media_id)
    except (ValueError, TypeError):
        return 'mediaId must be an integer', 400

    return media_type, media_id


def _resolve_or_abort():
    """Validate params and resolve video path. Returns (video_path,) or a Flask error tuple."""
    params = _validate_params()
    # _validate_params returns (str, int) on success or (error_msg, status_code) on failure.
    # On success media_type is "episode" or "movie", on error it's a longer message.
    if isinstance(params[0], str) and params[0] not in ('episode', 'movie'):
        return params

    media_type, media_id = params
    result = _resolve_video_path(media_type, media_id)
    if isinstance(result, tuple):
        return result

    video_path = result
    if not os.path.isfile(video_path):
        return 'Video file not found on disk', 404

    return (video_path,)


@api_ns_editor.route('editor/video')
class EditorVideo(Resource):
    @authenticate
    def get(self):
        """Stream video as fragmented MP4 for browser playback."""
        resolved = _resolve_or_abort()
        if len(resolved) == 2:
            return resolved

        video_path = resolved[0]

        # If frontend says the browser can play this file natively, serve it directly
        # This covers h264, hevc (on Safari/Edge), vp9 (Chrome), av1, etc.
        if request.args.get('direct') == '1':
            ext = os.path.splitext(video_path)[1].lower()
            mime_map = {'.mp4': 'video/mp4', '.m4v': 'video/mp4', '.webm': 'video/webm', '.mkv': 'video/x-matroska'}
            mime = mime_map.get(ext, 'video/mp4')
            return _serve_file_with_ranges(video_path, mime)

        # Remux or transcode on the fly with ffmpeg
        try:
            ffmpeg = _get_ffmpeg()
        except Exception:
            logger.exception('ffmpeg binary not available')
            return 'ffmpeg not found', 500

        # If frontend says remux=1, the browser can play the video codec natively,
        # just need audio transcoded to AAC. Copy video stream (very fast).
        if request.args.get('remux') == '1':
            video_args = ['-c:v', 'copy']
        else:
            # Check if the video codec can be copied or needs full transcode
            probe_data = _probe_video(video_path)
            video_codec = None
            if probe_data:
                for stream in probe_data.get('streams', []):
                    if stream.get('codec_type') == 'video':
                        video_codec = stream.get('codec_name', '').lower()
                        break

            if video_codec in ('h264', 'avc'):
                video_args = ['-c:v', 'copy']
            else:
                video_args = ['-c:v', 'libx264', '-preset', 'ultrafast', '-crf', '28', '-tune', 'fastdecode']

        # Support seeking via ?t= parameter (seconds)
        # Use -ss before -i for fast keyframe seek, then -ss after -i for precise frame
        pre_seek = []
        post_seek = []
        start_time = request.args.get('t')
        if start_time:
            try:
                t = float(start_time)
                if t > 0:
                    # Fast seek to 5s before target, then precise seek to exact frame
                    pre_seek = ['-ss', str(max(0, t - 5))]
                    post_seek = ['-ss', str(min(5, t))]
            except (ValueError, TypeError):
                pass

        cmd = [
            ffmpeg,
            *pre_seek,
            '-i', video_path,
            *post_seek,
            *video_args,
            '-c:a', 'aac',
            '-movflags', 'frag_keyframe+empty_moov+default_base_moof',
            '-f', 'mp4',
            '-v', 'error',
            'pipe:1',
        ]
        return _stream_ffmpeg(cmd, 'video/mp4')


@api_ns_editor.route('editor/audio')
class EditorAudio(Resource):
    @authenticate
    def get(self):
        """Extract audio track as AAC, cached as file for native seeking."""
        resolved = _resolve_or_abort()
        if len(resolved) == 2:
            return resolved

        video_path = resolved[0]

        import hashlib
        import threading
        file_stat = os.stat(video_path)
        path_hash = hashlib.md5(video_path.encode()).hexdigest()
        audio_cache_dir = os.path.join(PEAKS_CACHE_DIR, 'audio')
        os.makedirs(audio_cache_dir, exist_ok=True)
        cache_file = os.path.join(audio_cache_dir, f'{path_hash}_{int(file_stat.st_mtime)}.m4a')
        tmp_file = os.path.join(audio_cache_dir, f'{path_hash}_{int(file_stat.st_mtime)}.extracting.m4a')

        # Already cached: serve immediately
        if os.path.isfile(cache_file):
            return _serve_file_with_ranges(cache_file, 'audio/mp4')

        # Extraction in progress (tmp file exists): tell frontend to wait
        if os.path.isfile(tmp_file):
            return {'status': 'extracting'}, 202

        # Start extraction in background thread
        def extract():
            try:
                ffmpeg = _get_ffmpeg()
                cmd = [
                    ffmpeg,
                    '-i', video_path,
                    '-vn',
                    '-map', '0:a:0',
                    '-c:a', 'aac',
                    '-b:a', '24k',
                    '-ac', '1',
                    '-ar', '16000',
                    '-movflags', '+faststart',
                    '-v', 'error',
                    '-y',
                    tmp_file,
                ]
                result = subprocess.run(cmd, capture_output=True, timeout=600)
                if result.returncode == 0 and os.path.isfile(tmp_file):
                    os.replace(tmp_file, cache_file)
                    logger.info('Audio cache ready: %s (%d bytes)', cache_file, os.path.getsize(cache_file))
                else:
                    stderr_out = result.stderr.decode(errors='replace')[:500]
                    logger.error('Audio extraction failed: %s', stderr_out)
                    try:
                        os.unlink(tmp_file)
                    except OSError:
                        pass
            except Exception:
                logger.exception('Audio extraction error')
                try:
                    os.unlink(tmp_file)
                except OSError:
                    pass

        threading.Thread(target=extract, daemon=True).start()
        return {'status': 'extracting'}, 202


@api_ns_editor.route('editor/peaks')
class EditorPeaks(Resource):
    @authenticate
    def get(self):
        """Return pre-generated waveform peaks as JSON for wavesurfer.js."""
        resolved = _resolve_or_abort()
        if len(resolved) == 2:
            return resolved

        video_path = resolved[0]

        # Build a cache key from the file path and modification time
        stat = os.stat(video_path)
        # Use a stable filename derived from the video path
        import hashlib
        path_hash = hashlib.md5(video_path.encode()).hexdigest()
        cache_file = os.path.join(PEAKS_CACHE_DIR, f'{path_hash}_{int(stat.st_mtime)}.json')

        # Check cache
        if os.path.isfile(cache_file):
            try:
                with open(cache_file, 'r') as f:
                    return json.load(f)
            except (json.JSONDecodeError, OSError):
                # Corrupted cache, regenerate
                pass

        # Get duration first
        probe_data = _probe_video(video_path)
        if not probe_data:
            return 'Failed to probe video file', 500

        duration = None
        fmt = probe_data.get('format', {})
        if 'duration' in fmt:
            try:
                duration = float(fmt['duration'])
            except (ValueError, TypeError):
                pass

        if duration is None:
            return 'Could not determine video duration', 500

        # Generate peaks by having ffmpeg output low-rate PCM and processing in chunks.
        # Use 800Hz sample rate (much less data than 8000Hz) and produce ~10 peaks/sec.
        try:
            ffmpeg = _get_ffmpeg()
        except Exception:
            logger.exception('ffmpeg binary not available')
            return 'ffmpeg not found', 500

        sample_rate = 800
        target_rate = 10
        samples_per_peak = max(1, sample_rate // target_rate)  # 80 samples per peak
        chunk_bytes = samples_per_peak * 4  # 320 bytes per peak

        cmd = [
            ffmpeg,
            '-i', video_path,
            '-map', '0:a:0',
            '-ac', '1',
            '-ar', str(sample_rate),
            '-f', 'f32le',
            '-v', 'error',
            'pipe:1',
        ]

        peaks = []
        try:
            process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            while True:
                data = process.stdout.read(chunk_bytes)
                if not data:
                    break
                n = len(data) // 4
                if n == 0:
                    break
                chunk = struct.unpack(f'<{n}f', data[:n * 4])
                max_val = max(chunk, key=abs)
                peaks.append(round(max_val, 4))
            process.wait(timeout=10)
            if process.returncode != 0:
                stderr_out = process.stderr.read().decode(errors='replace')[:500]
                logger.error('ffmpeg peaks generation failed: %s', stderr_out)
                if not peaks:
                    return 'Failed to generate audio peaks', 500
        except subprocess.TimeoutExpired:
            if process.poll() is None:
                process.kill()
            if not peaks:
                return 'Peak generation timed out', 500

        if not peaks:
            return 'No audio data found in file', 500

        # Normalize to [-1, 1]
        max_abs = max(abs(p) for p in peaks)
        if max_abs > 0:
            peaks = [round(p / max_abs, 4) for p in peaks]

        response_data = {
            'peaks': peaks,
            'duration': round(duration, 2),
            'sampleRate': target_rate,
        }

        # Cache the result
        try:
            os.makedirs(PEAKS_CACHE_DIR, exist_ok=True)
            with open(cache_file, 'w') as f:
                json.dump(response_data, f)
        except OSError:
            logger.warning('Failed to cache peaks for %s', video_path)

        return response_data


@api_ns_editor.route('editor/info')
class EditorInfo(Resource):
    @authenticate
    def get(self):
        """Return video metadata for the editor UI."""
        resolved = _resolve_or_abort()
        if len(resolved) == 2:
            return resolved

        video_path = resolved[0]

        probe_data = _probe_video(video_path)
        if not probe_data:
            return 'Failed to probe video file', 500

        duration = None
        fmt = probe_data.get('format', {})
        if 'duration' in fmt:
            try:
                duration = float(fmt['duration'])
            except (ValueError, TypeError):
                pass

        video_codec = None
        audio_codec = None
        resolution = None

        for stream in probe_data.get('streams', []):
            codec_type = stream.get('codec_type')
            if codec_type == 'video' and video_codec is None:
                video_codec = stream.get('codec_name')
                width = stream.get('width')
                height = stream.get('height')
                if width and height:
                    resolution = f'{width}x{height}'
            elif codec_type == 'audio' and audio_codec is None:
                audio_codec = stream.get('codec_name')

        container = os.path.splitext(video_path)[1].lstrip('.').lower()

        return {
            'duration': round(duration, 2) if duration else None,
            'videoCodec': video_codec,
            'audioCodec': audio_codec,
            'resolution': resolution,
            'container': container,
        }
