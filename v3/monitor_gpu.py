import os
import subprocess
import requests
import time
import yaml
from dotenv import load_dotenv

# .env 파일 로드
load_dotenv('server_ex.env')

# 환경 변수 읽기
WEBHOOK_URL = os.getenv("SLACK_WEBHOOK_URL")
SERVER_NAME = os.getenv("SERVER_NAME", "Unknown Server")

if not WEBHOOK_URL:
    raise ValueError("SLACK_WEBHOOK_URL 환경 변수가 설정되지 않았습니다.")

# 설정 값
CHECK_INTERVAL = 60  # 1분 간격
ALERT_THRESHOLD = 5000  # 5GB (MB 단위)

# 데이터 저장 경로 설정
LOG_DIR = "monitor_log"
LOG_FILE = os.path.join(LOG_DIR, "gpu_status.log")
os.makedirs(LOG_DIR, exist_ok=True)

def get_gpu_memory_usage():
    """nvidia-smi 기본 명령으로 GPU 메모리 사용량 가져오기"""
    try:
        result = subprocess.run(["nvidia-smi"], capture_output=True, text=True)
        if result.returncode != 0:
            print("[ERROR] nvidia-smi 명령 실행 실패")
            return {}

        output = result.stdout
        gpu_usage = {}

        # GPU 정보 파싱
        lines = output.splitlines()
        gpu_index = -1
        for i, line in enumerate(lines):
            if "Tesla V100-SXM2-32GB" in line:  # GPU 모델 이름 기준으로 탐지
                gpu_index += 1
                gpu_usage[gpu_index] = 0  # 초기화
            elif gpu_index >= 0 and "MiB" in line and "Default" in line:  # 메모리 사용량 감지
                try:
                    parts = line.split("|")
                    memory_info = parts[2].strip()  # "Memory-Usage" 부분
                    used_memory = int(memory_info.split("/")[0].strip().replace("MiB", ""))
                    gpu_usage[gpu_index] = used_memory
                except (IndexError, ValueError) as e:
                    print(f"[ERROR] 메모리 사용량 파싱 실패: {line} ({e})")

        return gpu_usage
    except Exception as e:
        print(f"[ERROR] GPU 메모리 사용량 조회 중 오류 발생: {e}")
        return {}

def get_gpu_process_info():
    """nvidia-smi --query-compute-apps를 통해 GPU 프로세스 정보 가져오기"""
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-compute-apps=gpu_uuid,pid,used_memory", "--format=csv,noheader,nounits"],
            capture_output=True,
            text=True
        )
        if result.returncode != 0:
            print("[ERROR] nvidia-smi --query-compute-apps 명령 실행 실패")
            return {}

        lines = result.stdout.strip().split("\n")
        gpu_process_info = {}

        for line in lines:
            if not line.strip():
                continue

            gpu_uuid, pid, used_memory = line.split(", ")
            pid = int(pid)
            used_memory = int(used_memory)

            if gpu_uuid not in gpu_process_info:
                gpu_process_info[gpu_uuid] = {"used_memory": 0, "processes": []}

            gpu_process_info[gpu_uuid]["used_memory"] += used_memory
            gpu_process_info[gpu_uuid]["processes"].append({"pid": pid, "used_memory": used_memory})

        return gpu_process_info
    except Exception as e:
        print(f"[ERROR] GPU 프로세스 정보 조회 중 오류 발생: {e}")
        return {}

def get_process_cwd(pid):
    """특정 PID의 작업 디렉토리 가져오기"""
    try:
        cwd_path = os.readlink(f"/proc/{pid}/cwd")
        return cwd_path
    except FileNotFoundError:
        print(f"[DEBUG] PID {pid} 작업 디렉토리를 찾을 수 없습니다.")
        return None
    except Exception as e:
        print(f"[ERROR] PID {pid} 작업 디렉토리 확인 중 오류 발생: {e}")
        return None

def get_process_command(pid):
    """특정 PID의 명령줄 가져오기"""
    try:
        cmdline_path = f"/proc/{pid}/cmdline"
        with open(cmdline_path, "r") as f:
            cmdline = f.read().replace("\x00", " ").strip()
        return cmdline
    except FileNotFoundError:
        print(f"[DEBUG] PID {pid}에 대한 명령줄 파일을 찾을 수 없습니다: {cmdline_path}")
        return None
    except Exception as e:
        print(f"[ERROR] PID {pid} 명령줄 읽기 오류: {e}")
        return None

def extract_yaml_info(cmdline, cwd):
    """명령줄에서 YAML 파일 경로 추출 및 내용 읽기"""
    parts = cmdline.split()

    for part in parts:
        if part.endswith(".yaml") or part.endswith(".yml"):
            yaml_path = part
            abs_yaml_path = os.path.join(cwd, yaml_path) if not os.path.isabs(yaml_path) else yaml_path

            if os.path.exists(abs_yaml_path):
                try:
                    with open(abs_yaml_path, "r") as f:
                        yaml_data = yaml.safe_load(f)

                        model_info = yaml_data.get("model", {})
                        return {
                            "yaml_path": abs_yaml_path,
                            "llama_path": os.path.basename(model_info.get("llama_path", "N/A")),
                            "whisper_path": os.path.basename(model_info.get("whisper_path", "N/A")),
                            "beats_path": os.path.basename(model_info.get("beats_path", "N/A"))
                        }
                except yaml.YAMLError as e:
                    print(f"[ERROR] YAML 파일 파싱 오류: {abs_yaml_path}, 오류: {e}")
                except Exception as e:
                    print(f"[ERROR] YAML 파일 읽기 오류: {abs_yaml_path}, 오류: {e}")
            else:
                print(f"[DEBUG] YAML 파일 경로가 존재하지 않습니다: {abs_yaml_path}")
    return None

def save_to_file(data):
    """GPU 상태를 파일에 저장"""
    with open(LOG_FILE, "a") as f:
        f.write(data + "\n")

def send_to_slack(message):
    """슬랙으로 메시지 전송"""
    full_message = f"🖥️ *{SERVER_NAME}*\n{message}"
    requests.post(WEBHOOK_URL, json={"text": full_message})

def monitor_gpu():
    previous_states = {}  # 이전 GPU 상태 저장
    already_notified_complete = set()  # 학습 완료 알림 기록
    first_run = True

    while True:
        # 1단계: GPU 메모리 사용량 조회
        gpu_usage = get_gpu_memory_usage()
        if not gpu_usage:
            print("[GPU Monitor] GPU가 감지되지 않았습니다.")
            time.sleep(CHECK_INTERVAL)
            continue

        # 2단계: GPU 프로세스 정보 조회
        gpu_process_info = get_gpu_process_info()

        message_lines = []  # 슬랙 메시지 라인
        changes_detected = False  # 상태 변화 감지 여부
        task_mapping = {}  # PID와 작업 정보 매핑
        gpu_to_pid = {}  # GPU와 연결된 PID 매핑

        for gpu_index, used_memory in gpu_usage.items():
            emoji = f"{gpu_index}️⃣"
            previous_used = previous_states.get(gpu_index, 0)

            # GPU 상태에 따른 알림 처리
            if used_memory == 0:  # GPU 메모리가 0MB일 때
                if gpu_index not in already_notified_complete:
                    changes_detected = True
                    message_lines.append(f"{emoji} GPU {gpu_index}: 0MB ✅ 학습 완료")
                    already_notified_complete.add(gpu_index)
            else:  # GPU가 다시 사용 중일 경우
                if gpu_index in already_notified_complete:
                    already_notified_complete.discard(gpu_index)  # 완료 알림 초기화
                if abs(used_memory - previous_used) >= ALERT_THRESHOLD:
                    changes_detected = True
                    message_lines.append(
                        f"{emoji} GPU {gpu_index}: {used_memory}MB (변화: {previous_used}MB → {used_memory}MB)"
                    )

                # 프로세스별 정보 및 YAML 확인
                for gpu_uuid, gpu_data in gpu_process_info.items():
                    for process in gpu_data["processes"]:
                        pid = process["pid"]
                        cmdline = get_process_command(pid)
                        cwd = get_process_cwd(pid)

                        if cmdline and cwd:
                            yaml_info = extract_yaml_info(cmdline, cwd)
                            if yaml_info:
                                task_mapping[pid] = yaml_info
                                gpu_to_pid[gpu_index] = pid

            # GPU 사용량 업데이트
            previous_states[gpu_index] = used_memory

        # 동일한 작업인지 확인
        unique_tasks = set(
            (info["yaml_path"], info["llama_path"], info["whisper_path"], info["beats_path"])
            for info in task_mapping.values()
        )
        if len(unique_tasks) == 1:
            unique_task = next(iter(unique_tasks))
            message_lines.append(
                f":mag: 실행 중인 작업: {unique_task[0]}\n"
                f"- llama_path: {unique_task[1]}\n"
                f"- whisper_path: {unique_task[2]}\n"
                f"- beats_path: {unique_task[3]}"
            )
        else:
            # 서로 다른 작업 정보 개별 알림
            for gpu_index, pid in gpu_to_pid.items():
                if pid in task_mapping:
                    task_info = task_mapping[pid]
                    message_lines.append(
                        f"{gpu_index}️⃣ 실행 중인 작업: {task_info['yaml_path']}\n"
                        f"- llama_path: {task_info['llama_path']}\n"
                        f"- whisper_path: {task_info['whisper_path']}\n"
                        f"- beats_path: {task_info['beats_path']}"
                    )

        # 슬랙 알림 전송
        if first_run or changes_detected:
            if message_lines:  # 메시지가 있을 경우에만 알림 전송
                full_message = "\n".join(message_lines)
                send_to_slack(full_message)
                save_to_file(full_message)

        first_run = False
        time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    monitor_gpu()
