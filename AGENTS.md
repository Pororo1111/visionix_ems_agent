# Agents 운영 가이드

## 문서 목적

이 문서는 Visionix EMS 환경에서 동작하는 에이전트(Agent) 구성과 협업 시 유의사항을 정리한 가이드입니다. 에이전트 개발자와 운영자는 본 문서를 참고하여 일관된 방식으로 작업을 진행하십시오.

## 기본 원칙

-   모든 커뮤니케이션과 문서화, 코드 리뷰, 커밋 메시지는 **반드시 한국어**로 작성합니다.
-   에이전트는 라즈베리 파이 상의 검사 서버(CAMERA, HDMI, OCR, AC, DC)에서 수집한 상태 값을 Visionix EMS로 전달하는 역할을 수행합니다.
-   프로메테우스(Prometheus) 메트릭과 REST API는 앱 수준에서 정의된 규격을 유지해야 합니다.

## API 연동 요약

-   `POST /status`
    -   JSON 본문으로 상태 값을 갱신합니다. 예: `{"ocr_value": "12:34:56"}` 또는 `{"ocr_value": 45296}`
-   `GET /status/update`
    -   쿼리스트링으로 상태 값을 갱신합니다. 예: `/status/update?ocr_value=12:34:56`
-   `GET /status`
    -   현재 상태 스냅샷을 반환합니다.

## Prometheus 메트릭

-   `camera_value`, `ocr_value_seconds`, `hdmi_value`, `ac_value`, `dc_value` 게이지를 통해 장비 상태를 수집합니다.
-   OCR 문자열은 `ocr_value` Info 메트릭으로도 노출되며, 내부 저장은 초 단위 정수입니다.

## 개발 및 운영 체크리스트

1. **상태 값 규격 준수**: OCR은 0~86399 범위의 초 또는 `HH:MM:SS` 문자열만 사용해야 합니다.
2. **UI 검증**: `templates/index.html`에서 버튼과 입력 폼이 제대로 동작하는지 확인합니다.
3. **테스트 실행**: 변경 후 `python -m compileall app.py` 등 기본 검증을 수행합니다.
4. **커밋 규칙**: 커밋 메시지와 모든 설명은 한국어로 작성하고, 변경 사항과 테스트 결과를 명확히 기록합니다.
