import os
import shutil
import time
import uuid
import queue
import threading

from flask import Flask, render_template, request, jsonify, send_from_directory, Response, stream_with_context
from flask_cors import CORS
from models.fitting_model import (
    match_avatar, calc_export_shape_keys
)
from services.blender_runner import run_blender
from pipeline import run_pipeline, JobManifest

app = Flask(__name__)
CORS(app)

progress_queues = {}

GARMENT_FILE_MAP = {
    'tshirt': 'top',
    'hoodie': 'hoodie',
    'jacket': 'hoodie',
    'pants': 'pants',
    'trousers': 'pants',
    'shorts': 'pants',
    'skirt': 'pants',
}

UPLOAD_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'uploads')
os.makedirs(UPLOAD_DIR, exist_ok=True)


def generate_fit_text(fabric, stretch):
    """소재·신축성 기반 총평 텍스트 생성"""
    from models.fabric import build_fit_analysis
    return build_fit_analysis(str(fabric), stretch)

@app.route('/')
def index():
    return render_template('index.html')


@app.route('/result')
def result():
    return render_template('result.html')


@app.route('/api/fit/progress/<job_id>')
def progress(job_id):
    def generate():
        q = progress_queues.get(job_id)
        if not q:
            yield "data: done\n\n"
            return
        while True:
            msg = q.get()
            yield f"data: {msg}\n\n"
            if msg in ("done", "error"):
                progress_queues.pop(job_id, None)
                break
    return Response(stream_with_context(generate()), mimetype='text/event-stream')


@app.route('/outputs/<path:filename>')
def serve_output(filename):
    outputs_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'outputs')
    return send_from_directory(outputs_dir, filename)


def cleanup_outputs(max_age_seconds=1800):
    outputs_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'outputs')
    if not os.path.exists(outputs_dir):
        return
    now = time.time()
    for name in os.listdir(outputs_dir):
        folder = os.path.join(outputs_dir, name)
        if os.path.isdir(folder):
            age = now - os.path.getmtime(folder)
            if age > max_age_seconds:
                shutil.rmtree(folder, ignore_errors=True)
                print(f"[Cleanup] 삭제: {name} ({int(age)}초 경과)")


@app.route('/api/fit/analyze', methods=['POST'])
def analyze():
    try:
        body         = request.get_json()
        height       = body['height']
        weight       = body['weight']
        garment_type = body.get('garment_type', 'tshirt') or 'tshirt'
        measurements = body.get('measurements', {})
        fabric       = body.get('fabric', {})
        stretch      = body.get('stretch', '')

        cleanup_outputs()

        from models.fabric import resolve_fabric_props, normalize_fabric
        fabric_props = resolve_fabric_props(fabric, stretch)
        fabric = fabric_props["fabric"] or normalize_fabric(fabric)

        avatar_size       = match_avatar(height, weight)
        shape_keys_export = calc_export_shape_keys(garment_type, measurements)

        # 총평 텍스트 생성
        fabric_name          = fabric_props.get("summary_ko") or " ".join(fabric.keys())
        fit_analysis, summary = generate_fit_text(fabric_name, stretch)

        garment_file = GARMENT_FILE_MAP.get(garment_type, garment_type)

        job_id = str(uuid.uuid4())
        q      = queue.Queue()
        progress_queues[job_id] = q

        result_data = {
            "job_id":       job_id,
            "avatar_size":  avatar_size,
            "fit_analysis": fit_analysis,
            "summary":      summary,
            "images": {
                "silhouette_front": f"/outputs/{job_id}/silhouette_front.png",
                "silhouette_right": f"/outputs/{job_id}/silhouette_right.png",
                "silhouette_back":  f"/outputs/{job_id}/silhouette_back.png",
                "silhouette_left":  f"/outputs/{job_id}/silhouette_left.png",
            }
        }

        def run_in_background():
            try:
                run_blender({
                    "avatar_size":  avatar_size,
                    "garment_type": garment_file,
                    "shape_keys":   shape_keys_export,
                    "fabric":       fabric,
                    "stretch":      stretch,
                    "fabric_elasticity": fabric_props["elasticity"],
                    "fabric_bending":    fabric_props["bending"],
                }, job_id=job_id, q=q)
            except Exception:
                import traceback; traceback.print_exc()
                if q: q.put("error")

        threading.Thread(target=run_in_background, daemon=True).start()

        return jsonify(result_data)

    except KeyError as e:
        return jsonify({"error": f"필수 입력값 누락: {e}"}), 400
    except Exception as e:
        import traceback; traceback.print_exc()
        return jsonify({"error": f"서버 오류: {str(e)}"}), 500


@app.route('/api/pipeline/run', methods=['POST'])
def pipeline_run():
    """이미지(+치수) → 3D 의류 자동화 파이프라인.

    multipart: front/side/back 이미지 파일 + JSON 필드 `payload`
    또는 application/json: JobManifest (images는 서버 경로)
    """
    try:
        cleanup_outputs()

        if request.content_type and 'multipart/form-data' in request.content_type:
            payload_raw = request.form.get('payload') or '{}'
            import json as _json
            body = _json.loads(payload_raw)
            job_id = body.get('job_id') or str(uuid.uuid4())
            body['job_id'] = job_id
            img_dir = os.path.join(UPLOAD_DIR, job_id)
            os.makedirs(img_dir, exist_ok=True)
            images = body.get('images') or {}
            for view in ('front', 'side', 'back', 'detail'):
                f = request.files.get(view)
                if not f:
                    continue
                ext = os.path.splitext(f.filename or '')[1] or '.jpg'
                path = os.path.join(img_dir, f'{view}{ext}')
                f.save(path)
                images[view] = path
            body['images'] = images
        else:
            body = request.get_json(force=True, silent=False) or {}

        manifest = JobManifest.from_dict(body)
        job_id = manifest.job_id
        q = queue.Queue()
        progress_queues[job_id] = q

        def run_in_background():
            try:
                result = run_pipeline(manifest, q=q)
                # 결과를 job 폴더에 저장
                import json as _json
                out_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'outputs', job_id)
                os.makedirs(out_dir, exist_ok=True)
                with open(os.path.join(out_dir, 'job_result.json'), 'w', encoding='utf-8') as f:
                    _json.dump(result.to_dict(), f, ensure_ascii=False, indent=2)
            except Exception:
                import traceback; traceback.print_exc()
                if q: q.put('error')

        threading.Thread(target=run_in_background, daemon=True).start()

        return jsonify({
            'job_id': job_id,
            'status': 'running',
            'progress_url': f'/api/fit/progress/{job_id}',
            'result_url': f'/outputs/{job_id}/job_result.json',
            'images': {
                'silhouette_front': f'/outputs/{job_id}/silhouette_front.png',
                'silhouette_right': f'/outputs/{job_id}/silhouette_right.png',
                'silhouette_back':  f'/outputs/{job_id}/silhouette_back.png',
                'silhouette_left':  f'/outputs/{job_id}/silhouette_left.png',
            },
        })
    except KeyError as e:
        return jsonify({'error': f'필수 입력값 누락: {e}'}), 400
    except Exception as e:
        import traceback; traceback.print_exc()
        return jsonify({'error': f'서버 오류: {str(e)}'}), 500


@app.route('/api/pipeline/result/<job_id>', methods=['GET'])
def pipeline_result(job_id):
    out_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'outputs', job_id)
    path = os.path.join(out_dir, 'job_result.json')
    from pipeline.progress import read_progress
    prog = read_progress(out_dir)
    if not os.path.exists(path):
        return jsonify({
            'job_id': job_id,
            'status': 'running',
            'progress': prog or {'percent': 0, 'message': '대기 중...', 'stage': 'pending'},
        }), 202
    import json as _json
    with open(path, encoding='utf-8') as f:
        data = _json.load(f)
    if prog:
        data['progress'] = prog
    return jsonify(data)


@app.route('/api/pipeline/progress/<job_id>', methods=['GET'])
def pipeline_progress(job_id):
    """폴링용 진행률 JSON."""
    out_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'outputs', job_id)
    from pipeline.progress import read_progress
    prog = read_progress(out_dir)
    if not prog:
        return jsonify({'job_id': job_id, 'percent': 0, 'status': 'pending', 'message': '대기 중...'}), 202
    return jsonify({'job_id': job_id, **prog})


if __name__ == '__main__':
    app.run(debug=True, threaded=True, use_reloader=False)
