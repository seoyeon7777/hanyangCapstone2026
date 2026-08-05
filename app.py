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

# 디스크 워커 큐 (PIPELINE_QUEUE=disk|thread, 기본 disk)
try:
    from services.worker_queue import use_disk_queue, ensure_background_worker
    import os as _os
    if use_disk_queue() and _os.environ.get("PIPELINE_DISABLE_WORKER") not in ("1", "true", "yes"):
        ensure_background_worker(max_workers=int(_os.environ.get("PIPELINE_MAX_WORKERS", "1")))
except Exception as _e:
    print(f"[App] worker bootstrap skip: {_e}")


GARMENT_FILE_MAP = {
    'tshirt': 'top',
    'hoodie': 'hoodie',
    'jacket': 'hoodie',
    'pants': 'pants',
    'trousers': 'pants',
    'shorts': 'pants',
    'skirt': 'skirt',
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
        if q:
            while True:
                msg = q.get()
                yield f"data: {msg}\n\n"
                if msg in ("done", "error"):
                    progress_queues.pop(job_id, None)
                    break
            return

        # 디스크 워커 모드: progress.json 폴링으로 SSE 브리지
        from pipeline.progress import read_progress, format_progress_event
        out_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'outputs', job_id)
        last_pct = -1
        idle = 0
        while idle < 900:
            prog = read_progress(out_dir)
            if prog:
                pct = int(prog.get('percent') or 0)
                status = prog.get('status') or ''
                msg = prog.get('message') or ''
                if pct != last_pct:
                    yield f"data: {format_progress_event(pct, msg)}\n\n"
                    last_pct = pct
                if status in ('done', 'error', 'needs_review') or pct >= 100:
                    yield f"data: {'error' if status == 'error' else 'done'}\n\n"
                    break
                # job_result 존재도 종료 신호
                if os.path.exists(os.path.join(out_dir, 'job_result.json')) and pct >= 95:
                    yield "data: done\n\n"
                    break
            else:
                idle += 1
            time.sleep(0.8)
        else:
            yield "data: done\n\n"
    return Response(stream_with_context(generate()), mimetype='text/event-stream')


@app.route('/outputs/<path:filename>')
def serve_output(filename):
    outputs_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'outputs')
    return send_from_directory(outputs_dir, filename)


# 큐/잡 메타는 절대 cleanup 대상이 아님
_PROTECTED_OUTPUT_DIRS = {"_queue", "_jobs"}


def cleanup_outputs(max_age_seconds=1800):
    outputs_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'outputs')
    if not os.path.exists(outputs_dir):
        return
    now = time.time()
    for name in os.listdir(outputs_dir):
        if name in _PROTECTED_OUTPUT_DIRS or name.startswith('_'):
            continue
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

        from services.job_store import save_job, update_job
        from services.worker_queue import use_disk_queue, enqueue, queue_stats

        body_for_store = body if isinstance(body, dict) else manifest.to_dict()
        # ensure job_id in stored manifest
        if isinstance(body_for_store, dict):
            body_for_store = dict(body_for_store)
            body_for_store['job_id'] = job_id

        save_job(job_id, {
            "status": "queued" if use_disk_queue() else "running",
            "manifest": body_for_store,
            "retries": int((body_for_store or {}).get("_retries") or 0),
        })

        if use_disk_queue():
            enqueue("pipeline", body_for_store, job_id=job_id)
            # progress SSE may be empty until worker writes progress.json — poll API 사용
        else:
            def run_in_background():
                try:
                    result = run_pipeline(manifest, q=q)
                    import json as _json
                    out_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'outputs', job_id)
                    os.makedirs(out_dir, exist_ok=True)
                    with open(os.path.join(out_dir, 'job_result.json'), 'w', encoding='utf-8') as f:
                        _json.dump(result.to_dict(), f, ensure_ascii=False, indent=2)
                    update_job(
                        job_id,
                        status=result.status,
                        error=result.error,
                        result_path=os.path.join(out_dir, 'job_result.json'),
                    )
                except Exception as e:
                    import traceback; traceback.print_exc()
                    update_job(job_id, status="error", error=str(e))
                    if q: q.put('error')

            threading.Thread(target=run_in_background, daemon=True).start()

        return jsonify({
            'job_id': job_id,
            'status': 'queued' if use_disk_queue() else 'running',
            'queue': queue_stats() if use_disk_queue() else None,
            'progress_url': f'/api/fit/progress/{job_id}',
            'result_url': f'/outputs/{job_id}/job_result.json',
            'status_url': f'/api/pipeline/status/{job_id}',
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


@app.route('/api/pipeline/status/<job_id>', methods=['GET'])
def pipeline_status(job_id):
    from services.job_store import load_job
    from pipeline.progress import read_progress
    job = load_job(job_id)
    out_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'outputs', job_id)
    prog = read_progress(out_dir)
    if not job and not prog:
        return jsonify({'error': 'job not found', 'job_id': job_id}), 404
    payload = job or {'job_id': job_id}
    if prog:
        payload['progress'] = prog
    # manifest는 응답에서 생략 가능(용량) — 상태 위주
    slim = {k: v for k, v in payload.items() if k != 'manifest'}
    slim['has_manifest'] = bool(payload.get('manifest'))
    return jsonify(slim)


@app.route('/api/pipeline/jobs', methods=['GET'])
def pipeline_jobs():
    from services.job_store import list_recent
    limit = min(50, int(request.args.get('limit', 20)))
    jobs = list_recent(limit=limit)
    return jsonify({
        'jobs': [
            {
                'job_id': j.get('job_id'),
                'status': j.get('status'),
                'retries': j.get('retries', 0),
                'updated_at': j.get('updated_at'),
                'error': j.get('error'),
            }
            for j in jobs
        ]
    })


@app.route('/api/pipeline/retry/<job_id>', methods=['POST'])
def pipeline_retry(job_id):
    """실패한/검수필요 잡을 동일 manifest로 재실행."""
    from services.job_store import load_job, mark_retry, update_job, save_job
    from services.worker_queue import use_disk_queue, enqueue, queue_stats, ensure_background_worker

    job = load_job(job_id)
    if not job:
        return jsonify({'error': 'job not found'}), 404
    manifest_body = job.get('manifest')
    if not manifest_body:
        return jsonify({'error': '재시도용 manifest 없음'}), 400
    if job.get('status') == 'running':
        return jsonify({'error': '이미 실행 중'}), 409

    mark_retry(job_id)
    new_body = dict(manifest_body)
    new_body.pop('job_id', None)
    new_body['_retries'] = int(job.get('retries') or 0)
    new_body['_retry_of'] = job_id

    cleanup_outputs()
    manifest = JobManifest.from_dict(new_body)
    new_id = manifest.job_id
    new_body['job_id'] = new_id
    disk = use_disk_queue()
    q = queue.Queue()
    progress_queues[new_id] = q
    save_job(new_id, {
        'status': 'queued' if disk else 'running',
        'manifest': new_body,
        'retries': new_body['_retries'],
        'retry_of': job_id,
    })
    update_job(job_id, status='superseded', superseded_by=new_id)

    if disk:
        ensure_background_worker(
            max_workers=int(os.environ.get('PIPELINE_MAX_WORKERS', '1'))
        )
        enqueue('pipeline', new_body, job_id=new_id)
    else:
        def run_in_background():
            try:
                result = run_pipeline(manifest, q=q)
                import json as _json
                out_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'outputs', new_id)
                os.makedirs(out_dir, exist_ok=True)
                with open(os.path.join(out_dir, 'job_result.json'), 'w', encoding='utf-8') as f:
                    _json.dump(result.to_dict(), f, ensure_ascii=False, indent=2)
                update_job(new_id, status=result.status, error=result.error)
            except Exception as e:
                import traceback; traceback.print_exc()
                update_job(new_id, status='error', error=str(e))
                if q:
                    q.put('error')

        threading.Thread(target=run_in_background, daemon=True).start()

    return jsonify({
        'ok': True,
        'previous_job_id': job_id,
        'job_id': new_id,
        'status': 'queued' if disk else 'running',
        'queue': queue_stats() if disk else None,
        'progress_url': f'/api/fit/progress/{new_id}',
        'result_url': f'/api/pipeline/result/{new_id}',
    })


@app.route('/api/health', methods=['GET'])
def health():
    from services.worker_queue import queue_stats, use_disk_queue, reclaim_stale_running
    from services.job_store import list_recent
    from services.alerts import maybe_alert_queue
    from blender.config import BLENDER_PATH
    reclaimed = reclaim_stale_running()
    stats = queue_stats()
    maybe_alert_queue(stats)
    blender_ok = os.path.exists(BLENDER_PATH) if BLENDER_PATH else False
    backlog = int(stats.get('pending') or 0) + int(stats.get('running') or 0)
    stale = int(stats.get('stale_running') or 0)
    ok = bool(blender_ok) and stale == 0
    # 백로그만으로는 ok=false 하지 않음 (정상 대기). blender 없거나 stale이면 degraded.
    status_code = 200 if ok else 503
    body = {
        'ok': ok,
        'degraded': not ok,
        'blender_path': BLENDER_PATH,
        'blender_ok': blender_ok,
        'queue_mode': 'disk' if use_disk_queue() else 'thread',
        'queue': stats,
        'reclaimed': reclaimed,
        'backlog': backlog,
        'recent_jobs': len(list_recent(5)),
    }
    return jsonify(body), status_code


@app.route('/api/pipeline/queue', methods=['GET'])
def pipeline_queue():
    from services.worker_queue import queue_stats, use_disk_queue, reclaim_stale_running
    from services.alerts import maybe_alert_queue
    reclaimed = []
    if request.args.get('reclaim') in ('1', 'true', 'yes'):
        reclaimed = reclaim_stale_running()
    stats = queue_stats()
    maybe_alert_queue(stats)
    return jsonify({'mode': 'disk' if use_disk_queue() else 'thread', 'reclaimed': reclaimed, **stats})


@app.route('/api/pipeline/reclaim', methods=['POST'])
def pipeline_reclaim():
    """stuck running 잡을 pending으로 되돌림."""
    from services.worker_queue import reclaim_stale_running, queue_stats
    max_age = request.json.get('max_age_sec') if request.is_json else None
    if max_age is None:
        max_age = request.args.get('max_age_sec', type=float)
    reclaimed = reclaim_stale_running(max_age)
    return jsonify({'ok': True, 'reclaimed': reclaimed, 'queue': queue_stats()})


@app.route('/ops')
def ops_page():
    return render_template('ops.html')


@app.route('/api/ops/dashboard', methods=['GET'])
def ops_dashboard():
    """헬스+큐+정확도 스냅샷+최근 잡 요약."""
    from services.worker_queue import queue_stats, use_disk_queue, reclaim_stale_running
    from services.job_store import list_recent
    from blender.config import BLENDER_PATH, BASE_DIR
    import json as _json

    reclaim_stale_running()
    stats = queue_stats()
    blender_ok = os.path.exists(BLENDER_PATH) if BLENDER_PATH else False
    stale = int(stats.get('stale_running') or 0)
    health = {
        'ok': bool(blender_ok) and stale == 0,
        'blender_ok': blender_ok,
        'blender_path': BLENDER_PATH,
        'queue_mode': 'disk' if use_disk_queue() else 'thread',
        'queue': stats,
    }
    accuracy = {}
    for cand in (
        os.path.join(BASE_DIR, 'benchmarks', 'LAST_REPORT.json'),
        os.path.join(BASE_DIR, 'outputs', '_accuracy', 'accuracy_report.json'),
    ):
        if os.path.exists(cand):
            with open(cand, encoding='utf-8') as f:
                accuracy = _json.load(f)
            accuracy['_source'] = cand
            break

    progress = {
        'p0_percent': 99,
        'vision_percent': 78,
        'p1_percent': 88,
        'p2_percent': 8,
        'docs': '/docs not served — see docs/PROGRESS.md',
    }
    jobs = list_recent(10)
    slim_jobs = [
        {
            'job_id': j.get('job_id'),
            'status': j.get('status'),
            'updated_at': j.get('updated_at'),
            'error': j.get('error'),
            'retries': j.get('retries'),
        }
        for j in jobs
    ]
    return jsonify({
        'health': health,
        'accuracy': {
            'generated_at': accuracy.get('generated_at'),
            'use_blender': accuracy.get('use_blender'),
            'summary': accuracy.get('summary'),
            'source': accuracy.get('_source'),
        },
        'progress': progress,
        'recent_jobs': slim_jobs,
    })


@app.route('/benchmarks/<path:filename>')
def serve_benchmark_doc(filename):
    bench = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'benchmarks')
    return send_from_directory(bench, filename)


if __name__ == '__main__':
    app.run(debug=True, threaded=True, use_reloader=False)
