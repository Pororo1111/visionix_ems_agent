from flask import Flask, Response, request, jsonify, render_template
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST, Gauge, Counter, Histogram
import psutil
import time
import os

app = Flask(__name__)

# 시스템 메트릭 Gauge들
g_status = Gauge('camera_value', 'Camera status value')
g_cpu = Gauge('system_cpu_percent', 'System CPU usage percent')
g_mem = Gauge('system_memory_percent', 'System memory usage percent')
g_mem_available = Gauge('system_memory_available_bytes', 'Available memory in bytes')
g_mem_total = Gauge('system_memory_total_bytes', 'Total memory in bytes')
g_mem_used = Gauge('system_memory_used_bytes', 'Used memory in bytes')


# 디스크 메트릭
g_disk_usage = Gauge('system_disk_usage_percent', 'Disk usage percent', ['device', 'mountpoint'])
g_disk_free = Gauge('system_disk_free_bytes', 'Free disk space in bytes', ['device', 'mountpoint'])
g_disk_total = Gauge('system_disk_total_bytes', 'Total disk space in bytes', ['device', 'mountpoint'])

# 네트워크 메트릭
g_network_bytes_sent = Gauge('system_network_bytes_sent', 'Network bytes sent', ['interface'])
g_network_bytes_recv = Gauge('system_network_bytes_recv', 'Network bytes received', ['interface'])
g_network_packets_sent = Gauge('system_network_packets_sent', 'Network packets sent', ['interface'])
g_network_packets_recv = Gauge('system_network_packets_recv', 'Network packets received', ['interface'])

# 프로세스 메트릭
g_process_count = Gauge('system_process_count', 'Number of processes')
g_thread_count = Gauge('system_thread_count', 'Number of threads')

# 부팅 시간
g_boot_time = Gauge('system_boot_time_seconds', 'System boot time in seconds')

# HTTP 요청 메트릭
http_requests_total = Counter('http_requests_total', 'Total HTTP requests', ['method', 'endpoint', 'status'])
http_request_duration = Histogram('http_request_duration_seconds', 'HTTP request duration in seconds')


def collect_system_metrics():
    # 1분 평균 CPU 사용률(%)
    try:
        load1, _, _ = psutil.getloadavg()
        cpu_count = psutil.cpu_count() or 1
        g_cpu.set((load1 / cpu_count) * 100)
    except Exception:
        pass
    
    # 메모리 사용률 업데이트
    mem = psutil.virtual_memory()
    g_mem.set(mem.percent)
    g_mem_available.set(mem.available)
    g_mem_total.set(mem.total)
    g_mem_used.set(mem.used)
    
    # 디스크 메트릭 수집
    for partition in psutil.disk_partitions():
        try:
            usage = psutil.disk_usage(partition.mountpoint)
            g_disk_usage.labels(device=partition.device, mountpoint=partition.mountpoint).set(usage.percent)
            g_disk_free.labels(device=partition.device, mountpoint=partition.mountpoint).set(usage.free)
            g_disk_total.labels(device=partition.device, mountpoint=partition.mountpoint).set(usage.total)
        except (PermissionError, FileNotFoundError):
            continue
    
    # 네트워크 메트릭 수집
    net_io = psutil.net_io_counters(pernic=True)
    for interface, stats in net_io.items():
        g_network_bytes_sent.labels(interface=interface).set(stats.bytes_sent)
        g_network_bytes_recv.labels(interface=interface).set(stats.bytes_recv)
        g_network_packets_sent.labels(interface=interface).set(stats.packets_sent)
        g_network_packets_recv.labels(interface=interface).set(stats.packets_recv)
    
    # 프로세스 및 스레드 수
    g_process_count.set(len(psutil.pids()))
    g_thread_count.set(psutil.cpu_count() or 0)
    
    # 부팅 시간
    g_boot_time.set(psutil.boot_time())

@app.route('/metrics')
@http_request_duration.time()
def metrics():
    # 시스템 메트릭 수집
    collect_system_metrics()
    
    # HTTP 요청 카운터 증가
    http_requests_total.labels(method='GET', endpoint='/metrics', status='200').inc()
    
    data = generate_latest()
    return Response(data, mimetype=CONTENT_TYPE_LATEST)

@app.route('/status', methods=['POST'])
@http_request_duration.time()
def update_status():
    try:
        data = request.get_json()
        if not data or 'status' not in data:
            http_requests_total.labels(method='POST', endpoint='/status', status='400').inc()
            return jsonify({'error': 'status 값이 필요합니다'}), 400
        
        status_value = data['status']
        
        # status 값이 숫자인지 확인
        if not isinstance(status_value, (int, float)):
            http_requests_total.labels(method='POST', endpoint='/status', status='400').inc()
            return jsonify({'error': 'status 값은 숫자여야 합니다'}), 400
        
        # g_status 값 업데이트
        g_status.set(status_value)
        
        http_requests_total.labels(method='POST', endpoint='/status', status='200').inc()
        return jsonify({
            'message': 'Status updated successfully',
            'status': status_value,
            'timestamp': time.time()
        }), 200
        
    except Exception as e:
        http_requests_total.labels(method='POST', endpoint='/status', status='500').inc()
        return jsonify({'error': str(e)}), 500

@app.route('/status', methods=['GET'])
@http_request_duration.time()
def get_status():
    try:
        # 현재 g_status 값 조회
        current_status = g_status._value.get()
        
        http_requests_total.labels(method='GET', endpoint='/status', status='200').inc()
        return jsonify({
            'status': current_status,
            'timestamp': time.time()
        }), 200
        
    except Exception as e:
        http_requests_total.labels(method='GET', endpoint='/status', status='500').inc()
        return jsonify({'error': str(e)}), 500



@app.route('/')
@http_request_duration.time()
def index():
    # 기본 페이지
    http_requests_total.labels(method='GET', endpoint='/', status='200').inc()
    return render_template('index.html')

if __name__ == '__main__':
    import webbrowser
    from threading import Timer
    
    def open_browser():
        webbrowser.open('http://localhost:5000')
    
    # 서버가 시작된 후 0.5초 후에 브라우저 열기
    Timer(0.5, open_browser).start()
    
    # 서버 시작
    app.run(host='0.0.0.0', port=5000, debug=True)