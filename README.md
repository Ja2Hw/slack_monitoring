## 🖥️ GPU & Disk Monitoring with Slack 🖥️
우분투 환경 서버의 디스크 사용량과 GPU 사용량을 슬랙으로 알려주는 프로그램입니다.

블로그에 슬랙 API를 비롯한 좀 더 자세한 내용을 기록하였습니다.
- [Ja2Hw Dev-log :: 서버 사용 현황 모니터링 후 슬랙 봇으로 알려주기](https://ja2hw.tistory.com/6)

<br>

## v0
- 단일 GPU 모니터링: `get_gpu_memory()` 함수로 하나의 GPU만 조회

- GPU 메모리 상태 플래그: `alert_sent_for_idle` 전역 변수로 GPU 사용 가능 상태 메시지 중복 방지

- 상태 변화 감지 방식:
  - GPU 메모리가 0MB로 감소하는 경우 "사용 가능" 알림
  - GPU 메모리가 0MB에서 증가하는 경우 "학습 시작" 알림
  - 메모리 사용량 변화가 5GB 이상인 경우 변화량 알림

- 초기 실행 시 상태 보고: 프로그램 첫 실행 시 현재 GPU 상태 보고

<br>

## v1
- 다중 GPU 모니터링: `get_all_gpu_memory()` 함수로 여러 GPU 동시 모니터링

- GPU별 상태 관리:
  - 전역 플래그 없이 GPU별로 개별적인 이전 상태 관리
  - `previous_states` 리스트로 각 GPU의 이전 상태 저장

- 상태 변화 감지 및 알림 방식:
  - 사용량이 0MB로 감소한 경우 "사용 가능" 상태로 표시
  - 사용량이 0MB에서 증가하고 변화량이 5GB 이상일 때 "사용 시작" 표시
  - 일반적인 사용량 변화가 5GB 이상일 때 변화량 표시

- GPU별 이모지 표시: 각 GPU 번호에 해당하는 이모지 사용 (0️⃣, 1️⃣ 등)

<br>

## v2
- GPU 메모리 사용량 직접 파싱:
  - `nvidia-smi` 명령어 출력을 직접 파싱하여 GPU 상태 확인
  - 특정 GPU 모델(Tesla V100-SXM2-32GB) 기준으로 탐지

- GPU 프로세스 정보 수집:
  - `nvidia-smi --query-compute-apps` 명령어로 GPU 사용 프로세스 정보 수집
  - GPU UUID, PID, 사용 메모리 정보 획득

- 프로세스 작업 정보 수집:
  - PID의 작업 디렉토리와 명령줄 정보 수집
  - 명령줄에서 YAML 파일 경로 추출 및 내용 분석

- 작업 정보 분석:
  - YAML 파일에서 llama_path, whisper_path, beats_path 정보 추출
  - 동일 작업인지 다른 작업인지 구분

- 학습 완료 알림 관리:
  - `already_notified_complete` 세트로 이미 알림이 발송된 GPU 추적
  - GPU 사용량이 0MB일 때 학습 완료 알림 발송 (중복 방지)

<br><br>

## 파일 버전 간 monitor_gpu 차이 비교

| 기능 \ 버전 | v0 | v1 | v2 |
|------------|----------------|-----------------|-------------------|
| GPU 감지 함수 | get_gpu_memory() | get_all_gpu_memory() | get_gpu_memory_usage() |
| 메모리 획득 명령어 | nvidia-smi --query-gpu | nvidia-smi --query-gpu | nvidia-smi 출력 직접 파싱 |
| 모니터링 대상 | 단일 GPU | 다중 GPU | 다중 GPU(모델명 기준 탐지) |
| 상태 관리 변수 | alert_sent_for_idle (전역 boolean) | previous_states (리스트) | previous_states (딕셔너리), already_notified_complete (세트) |
| 알림 조건 | 사용량 0MB 또는 5GB 이상 변화 | 사용량 0MB 또는 5GB 이상 변화 | 사용량 0MB 또는 5GB 이상 변화 + 작업 정보 |
| 프로세스 정보 | 수집 안 함 | 수집 안 함 | GPU UUID, PID, 메모리 수집 |
| 작업 정보 | 수집 안 함 | 수집 안 함 | YAML 파일 분석 (모델 경로 수집) |
| YAML 분석 | 없음 | 없음 | llama_path, whisper_path, beats_path 추출 |
| 메시지 포맷 | 단일 GPU 기준 포맷 | 다중 GPU 통합 포맷 | 다중 GPU + 작업 정보 포맷 |

<br>
