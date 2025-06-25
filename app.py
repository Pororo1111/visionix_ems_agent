from flask import Flask, Response
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST, Gauge
import psutil

app = Flask(__name__)

# 기본 레지스트리 사용 (커스텀 레지스트리 제거)
g_status = Gauge('app_status', 'Application status')
g_cpu = Gauge('system_cpu_percent', 'System CPU usage percent')
g_mem = Gauge('system_memory_percent', 'System memory usage percent')

def collect_system_metrics():
    # CPU 사용률 업데이트
    cpu_percent = psutil.cpu_percent(interval=0.1)
    g_cpu.set(cpu_percent)
    # 메모리 사용률 업데이트
    mem = psutil.virtual_memory()
    g_mem.set(mem.percent)

@app.route('/metrics')
def metrics():
    # 시스템 메트릭 수집
    collect_system_metrics()
    # status 값 설정 (예시: 1=정상, 0=비정상)
    g_status.set(1)
    data = generate_latest()
    return Response(data, mimetype=CONTENT_TYPE_LATEST)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000) 