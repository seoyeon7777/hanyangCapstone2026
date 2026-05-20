import os
import shutil
import time
import uuid
import queue
import threading
from flask import Flask, render_template, request, jsonify, send_from_directory, Response, stream_with_context
from flask_cors import CORS
from models.fitting_model import match_avatar, calc_shape_keys, calc_scale, calc_fit_score, calc_pressure
from services.blender_runner import run_blender

app = Flask(__name__)
CORS(app)

progress_queues = {}

GARMENT_FILE_MAP = {
    'tshirt':  'top',
    'shirt':   'top',
    'hoodie':  'top',
    'jacket':  'top',
    'coat':    'top',
    'pants':   'pants',
}


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

        cleanup_outputs()

        avatar_size               = match_avatar(height, weight)
        shape_keys                = calc_shape_keys(garment_type, measurements, avatar_size)
        scale                     = calc_scale(garment_type, measurements)
        fit_score                 = calc_fit_score(shape_keys, fabric)
        pressure_data, fit_result = calc_pressure(shape_keys, fabric)

        garment_file = GARMENT_FILE_MAP.get(garment_type, garment_type)

        job_id = str(uuid.uuid4())
        q = queue.Queue()
        progress_queues[job_id] = q

        # 결과 데이터 미리 구성
        result_data = {
            "job_id":        job_id,
            "avatar_size":   avatar_size,
            "shape_keys":    shape_keys,
            "scale":         scale,
            "fit_score":     fit_score,
            "fit_result":    fit_result,
            "pressure_data": pressure_data,
            "images": {
                "silhouette_front": f"/outputs/{job_id}/silhouette_front.png",
                "silhouette_right": f"/outputs/{job_id}/silhouette_right.png",
                "silhouette_back":  f"/outputs/{job_id}/silhouette_back.png",
                "silhouette_left":  f"/outputs/{job_id}/silhouette_left.png",
            }
        }

        # 백그라운드에서 blender 실행
        def run_in_background():
            try:
                run_blender({
                    "avatar_size":   avatar_size,
                    "garment_type":  garment_file,
                    "shape_keys":    shape_keys,
                    "fabric":        fabric,
                }, job_id=job_id, q=q)
            except Exception as e:
                import traceback; traceback.print_exc()
                if q: q.put("error")

        threading.Thread(target=run_in_background, daemon=True).start()

        return jsonify(result_data)

    except KeyError as e:
        return jsonify({"error": f"필수 입력값 누락: {e}"}), 400
    except Exception as e:
        import traceback; traceback.print_exc()
        return jsonify({"error": f"서버 오류: {str(e)}"}), 500


if __name__ == '__main__':
    app.run(debug=True, threaded=True, use_reloader=False)