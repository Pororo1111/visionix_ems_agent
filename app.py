from flask import Flask, Response, request, jsonify, render_template
from prometheus_client import (
    generate_latest,
    CONTENT_TYPE_LATEST,
    Gauge,
    Counter,
    Histogram,
    Info,
)
import psutil
import time
from datetime import datetime, timedelta, timezone
import threading
import re
import math
import os
import json
from urllib import request as urlrequest
from urllib.error import URLError, HTTPError
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError as FuturesTimeout

app = Flask(__name__)

logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s %(name)s: %(message)s',
)
logger = logging.getLogger('visionix.agent')

# 상태 값 기본 설정
DEFAULT_STATUS = {
    'camera_value': 0,
    'ocr_value': 0,
    'hdmi_value': 0,
    'ac_value': 0,
    'dc_value': 0,
}
_status_state = DEFAULT_STATUS.copy()
_status_lock = threading.Lock()

# 시스템 메트릭 Gauge들
g_camera_value = Gauge('camera_value', 'Camera status value')
g_ocr_seconds = Gauge('ocr_value_seconds', 'OCR timestamp converted to seconds')
info_ocr_value = Info('ocr_value', 'OCR timestamp value as HH:MM:SS string')
g_hdmi_value = Gauge('hdmi_value', 'HDMI status value')
g_ac_value = Gauge('ac_value', 'AC power status value')
g_dc_value = Gauge('dc_value', 'DC power status value')

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


OCR_PATTERN = re.compile(r'^\d{1,2}:\d{2}:\d{2}$')

# 고정 KST(+09:00) 타임존
KST = timezone(timedelta(hours=9))


def _hms_to_seconds(value: str) -> int:
    hours, minutes, seconds = value.split(':')
    return int(hours) * 3600 + int(minutes) * 60 + int(seconds)


def _seconds_to_hms(value: int) -> str:
    seconds = max(0, int(value))
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    remaining = seconds % 60
    return f"{hours:02d}:{minutes:02d}:{remaining:02d}"


def _hms_kst_to_epoch_seconds(value: str) -> int:
    hours, minutes, seconds = map(int, value.split(':'))
    today_kst = datetime.now(tz=KST).date()
    dt_kst = datetime(
        year=today_kst.year,
        month=today_kst.month,
        day=today_kst.day,
        hour=hours,
        minute=minutes,
        second=seconds,
        tzinfo=KST,
    )
    return int(dt_kst.timestamp())


def _epoch_seconds_to_hms_kst(epoch_seconds: int) -> str:
    try:
        dt_kst = datetime.fromtimestamp(int(epoch_seconds), tz=KST)
    except (OverflowError, OSError, ValueError):  # 범위를 벗어난 경우 방어
        return "00:00:00"
    return dt_kst.strftime("%H:%M:%S")


def _update_metric(field: str, value):
    if field == 'camera_value':
        g_camera_value.set(value)
    elif field == 'ocr_value':
        # value는 이제 '에폭 초'로 저장/표시
        info_ocr_value.info({'value': _epoch_seconds_to_hms_kst(value)})
        g_ocr_seconds.set(value)
    elif field == 'hdmi_value':
        g_hdmi_value.set(value)
    elif field == 'ac_value':
        g_ac_value.set(value)
    elif field == 'dc_value':
        g_dc_value.set(value)


def _set_status(field: str, value):
    with _status_lock:
        _status_state[field] = value
    _update_metric(field, value)


def _get_status_snapshot():
    with _status_lock:
        return dict(_status_state)


def _validate_and_cast(field: str, raw_value):
    if field == 'ocr_value':
        if isinstance(raw_value, str):
            if not OCR_PATTERN.match(raw_value):
                raise ValueError('ocr_value must follow HH:MM:SS format')
            # 문자열(HH:MM:SS)은 '오늘 KST 기준 시각'으로 간주하여 에폭 초로 변환
            value = _hms_kst_to_epoch_seconds(raw_value)
        elif isinstance(raw_value, (int, float)):
            if not math.isfinite(raw_value):
                raise ValueError('ocr_value must be a finite number or HH:MM:SS string')
            # 숫자는 '에폭 초'로 간주
            value = int(raw_value)
        else:
            raise ValueError('ocr_value must be a HH:MM:SS string or number of seconds')
        if value < 0:
            raise ValueError('ocr_value must be zero or positive')
        return value

    try:
        value = int(raw_value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f'{field} must be an integer') from exc

    if field == 'camera_value':
        if value < 0:
            raise ValueError('camera_value must be zero or positive')
        return value
    if field == 'hdmi_value':
        if value not in {0, 1, 2, 3}:
            raise ValueError('hdmi_value must be one of 0, 1, 2, 3')
        return value
    if field in {'ac_value', 'dc_value'}:
        if value not in {0, 1}:
            raise ValueError(f'{field} must be either 0 or 1')
        return value
    raise ValueError(f'Unsupported field: {field}')


def _apply_updates(data: dict):
    updated_fields = {}
    for key in DEFAULT_STATUS:
        if key in data:
            value = _validate_and_cast(key, data[key])
            _set_status(key, value)
            updated_fields[key] = value
    if not updated_fields:
        raise ValueError('No valid fields provided for update')
    return updated_fields


def collect_system_metrics():
    cpu_percent = psutil.cpu_percent(interval=None)
    g_cpu.set(cpu_percent)

    mem = psutil.virtual_memory()
    g_mem.set(mem.percent)
    g_mem_available.set(mem.available)
    g_mem_total.set(mem.total)
    g_mem_used.set(mem.used)

    for partition in psutil.disk_partitions():
        try:
            usage = psutil.disk_usage(partition.mountpoint)
            g_disk_usage.labels(device=partition.device, mountpoint=partition.mountpoint).set(usage.percent)
            g_disk_free.labels(device=partition.device, mountpoint=partition.mountpoint).set(usage.free)
            g_disk_total.labels(device=partition.device, mountpoint=partition.mountpoint).set(usage.total)
        except (PermissionError, FileNotFoundError):
            continue

    net_io = psutil.net_io_counters(pernic=True)
    for interface, stats in net_io.items():
        g_network_bytes_sent.labels(interface=interface).set(stats.bytes_sent)
        g_network_bytes_recv.labels(interface=interface).set(stats.bytes_recv)
        g_network_packets_sent.labels(interface=interface).set(stats.packets_sent)
        g_network_packets_recv.labels(interface=interface).set(stats.packets_recv)

    g_process_count.set(len(psutil.pids()))
    g_thread_count.set(psutil.cpu_count() or 0)
    g_boot_time.set(psutil.boot_time())


def _initialize_metrics():
    snapshot = _get_status_snapshot()
    for key, value in snapshot.items():
        _update_metric(key, value)


_initialize_metrics()


@app.route('/metrics')
@http_request_duration.time()
def metrics():
    collect_system_metrics()
    http_requests_total.labels(method='GET', endpoint='/metrics', status='200').inc()
    data = generate_latest()
    return Response(data, mimetype=CONTENT_TYPE_LATEST)


@app.route('/status', methods=['POST'])
@http_request_duration.time()
def update_status():
    try:
        data = request.get_json(force=True, silent=True) or {}
        if 'status' in data and 'camera_value' not in data:
            data['camera_value'] = data['status']
        updated_fields = _apply_updates(data)
        response = {
            'status': _get_status_snapshot(),
            'updated_fields': list(updated_fields.keys()),
            'timestamp': time.time(),
        }
        http_requests_total.labels(method='POST', endpoint='/status', status='200').inc()
        return jsonify(response), 200
    except ValueError as exc:
        http_requests_total.labels(method='POST', endpoint='/status', status='400').inc()
        return jsonify({'error': str(exc)}), 400
    except Exception as exc:  # pragma: no cover
        http_requests_total.labels(method='POST', endpoint='/status', status='500').inc()
        return jsonify({'error': str(exc)}), 500


@app.route('/status', methods=['GET'])
@http_request_duration.time()
def get_status():
    try:
        http_requests_total.labels(method='GET', endpoint='/status', status='200').inc()
        return jsonify({
            'status': _get_status_snapshot(),
            'timestamp': time.time(),
        }), 200
    except Exception as exc:  # pragma: no cover
        http_requests_total.labels(method='GET', endpoint='/status', status='500').inc()
        return jsonify({'error': str(exc)}), 500


@app.route('/status/update', methods=['GET'])
@http_request_duration.time()
def update_status_via_get():
    try:
        query_params = request.args.to_dict()
        updated_fields = _apply_updates(query_params)
        response = {
            'status': _get_status_snapshot(),
            'updated_fields': list(updated_fields.keys()),
            'timestamp': time.time(),
        }
        http_requests_total.labels(method='GET', endpoint='/status/update', status='200').inc()
        return jsonify(response), 200
    except ValueError as exc:
        http_requests_total.labels(method='GET', endpoint='/status/update', status='400').inc()
        return jsonify({'error': str(exc)}), 400
    except Exception as exc:  # pragma: no cover
        http_requests_total.labels(method='GET', endpoint='/status/update', status='500').inc()
        return jsonify({'error': str(exc)}), 500


@app.route('/')
@http_request_duration.time()
def index():
    http_requests_total.labels(method='GET', endpoint='/', status='200').inc()
    return render_template('index.html')


def _fetch_json(url: str, timeout: float = 3.0):
    try:
        with urlrequest.urlopen(url, timeout=timeout) as resp:
            if resp.status != 200:
                return None
            data = resp.read().decode('utf-8')
            return json.loads(data)
    except (URLError, HTTPError, TimeoutError, json.JSONDecodeError):
        return None


def _poll_devices_loop():
    host_default = os.getenv('DEVICE_HOST', '127.0.0.1')
    hosts = {
        'camera': os.getenv('CAMERA_HOST', host_default),
        'hdmi': os.getenv('HDMI_HOST', host_default),
        'ocr': os.getenv('OCR_HOST', host_default),
        'ac': os.getenv('AC_HOST', host_default),
        'dc': os.getenv('DC_HOST', host_default),
    }
    ports = {
        'camera': int(os.getenv('CAMERA_PORT', '5001')),
        'hdmi': int(os.getenv('HDMI_PORT', '5002')),
        'ocr': int(os.getenv('OCR_PORT', '5003')),
        'ac': int(os.getenv('AC_PORT', '5004')),
        'dc': int(os.getenv('DC_PORT', '5005')),
    }

    # 실행 중 재사용할 스레드 풀 (최대 동시 5개)
    executor = ThreadPoolExecutor(max_workers=5, thread_name_prefix='fetch')

    while True:
        try:
            payload = {}

            # 요청 대상과 기대 키 매핑
            targets = {
                'camera': (f"http://{hosts['camera']}:{ports['camera']}/status", 'camera_value'),
                'hdmi': (f"http://{hosts['hdmi']}:{ports['hdmi']}/status", 'hdmi_value'),
                'ocr': (f"http://{hosts['ocr']}:{ports['ocr']}/status", 'ocr_value'),
                'ac': (f"http://{hosts['ac']}:{ports['ac']}/status", 'ac_value'),
                'dc': (f"http://{hosts['dc']}:{ports['dc']}/status", 'dc_value'),
            }

            futures = {}
            for name, (url, expect_key) in targets.items():
                fut = executor.submit(_fetch_json, url)
                futures[fut] = (name, expect_key)

            completed_names = set()
            try:
                for fut in as_completed(futures, timeout=3.0):
                    name, expect_key = futures[fut]
                    completed_names.add(name)
                    try:
                        data = fut.result()
                    except Exception as exc:  # noqa: BLE001
                        logger.warning("%s 서버 요청 실패: %s", name, exc)
                        continue

                    if data and expect_key in data:
                        payload[expect_key] = data[expect_key]
                        logger.info("%s 서버 값 수집 성공: %s", name, data[expect_key])
                    else:
                        logger.warning("%s 서버 값 수집 실패: %s", name, data)
            except FuturesTimeout:
                # 타임아웃으로 완료 못한 작업 로깅
                pass

            # 타임아웃 등으로 미완료된 대상 경고 처리
            for name, (_url, expect_key) in targets.items():
                if name not in completed_names:
                    logger.warning("%s 서버 요청 타임아웃", name)

            if payload:
                try:
                    _apply_updates(payload)
                except ValueError as exc:
                    logger.warning("수집 데이터 적용 실패: %s", exc)
        except Exception:
            logger.exception("장비 폴링 루프 처리 중 예외 발생")

        time.sleep(5)


_poller_started = False
_poller_lock = threading.Lock()

def _start_poller_thread_once():
    global _poller_started
    with _poller_lock:
        if _poller_started:
            return
        t = threading.Thread(target=_poll_devices_loop, name='device-poller', daemon=True)
        t.start()
        _poller_started = True

@app.before_request
def _ensure_poller_started():
    _start_poller_thread_once()


if __name__ == '__main__':
    import webbrowser
    from threading import Timer

    def open_browser():
        webbrowser.open('http://localhost:5000')

    Timer(0.5, open_browser).start()
    app.run(host='0.0.0.0', port=5000, debug=True)
