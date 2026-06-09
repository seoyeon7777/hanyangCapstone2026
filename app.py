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

app = Flask(__name__)
CORS(app)

progress_queues = {}

GARMENT_FILE_MAP = {
    'tshirt': 'top',
}


def generate_fit_text(fabric, stretch):
    """소재·신축성 기반 총평 텍스트 생성"""
    fabric_name = str(fabric)
    analysis    = []

    # 소재 기반 분석
    if "실크" in fabric_name or "silk" in fabric_name:
        analysis.append("실크 소재는 부드럽지만 신축성이 낮아 여유 있는 착용을 추천합니다.")
    if "린넨" in fabric_name or "linen" in fabric_name:
        analysis.append("린넨 소재는 통기성이 좋지만 구김과 수축 가능성이 있어 약간 여유 있는 핏이 적합합니다.")
    if "데님" in fabric_name or "denim" in fabric_name:
        analysis.append("데님 소재는 초기 착용 시 다소 뻣뻣할 수 있으나 착용하며 자연스럽게 몸에 맞춰집니다.")
    if "나일론" in fabric_name or "nylon" in fabric_name:
        analysis.append("나일론 소재는 가볍고 내구성이 높지만 통풍이 적어 타이트하면 답답할 수 있습니다.")
    if "코튼" in fabric_name or "cotton" in fabric_name:
        analysis.append("면 소재는 무난한 착용감을 제공하며 일상복에 적합합니다.")
    if "울" in fabric_name or "wool" in fabric_name:
        analysis.append("울 소재는 보온성이 좋고 고급스러운 착용감을 주지만 수축 가능성이 있어 약간 여유 있는 착용을 추천합니다.")
    if "폴리" in fabric_name or "폴리에스터" in fabric_name or "poly" in fabric_name or "polyester" in fabric_name:
        analysis.append("폴리에스터 소재는 구김이 적고 관리가 쉬우며 형태 유지가 좋지만, 통기성이 낮을 수 있어 타이트한 핏은 답답하게 느껴질 수 있습니다.")

    # 신축성 기반 분석
    if stretch in ["낮음", "신축성 없음", "X", "없음"]:
        analysis.append("신축성이 낮아 움직임 시 타이트하게 느껴질 수 있습니다.")
    elif stretch in ["높음", "좋음", "우수"]:
        analysis.append("신축성이 좋아 활동성이 우수할 것으로 예상됩니다.")

    summary = " ".join(analysis)
    return analysis, summary


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

        avatar_size       = match_avatar(height, weight)
        shape_keys_export = calc_export_shape_keys(garment_type, measurements)

        # 총평 텍스트 생성
        fabric_name          = " ".join(fabric.keys()) if isinstance(fabric, dict) else str(fabric)
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


if __name__ == '__main__':
    app.run(debug=True, threaded=True, use_reloader=False)
