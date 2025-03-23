from multiprocessing import Process
from slack_monitoring.v3.monitor_gpu import monitor_gpu
from monitor_disk import monitor_disk

if __name__ == "__main__":
    # GPU 모니터링 프로세스
    print("[Monitor] GPU 모니터링 프로세스 시작...")
    gpu_process = Process(target=monitor_gpu)
    
    # 디스크 모니터링 프로세스
    print("[Monitor] 디스크 모니터링 프로세스 시작...")
    disk_process = Process(target=monitor_disk)
    
    # 프로세스 시작
    gpu_process.start()
    disk_process.start()
    
    print("[Monitor] 모든 모니터링 프로세스가 정상적으로 실행 중입니다.")
    
    # 프로세스가 종료될 때까지 대기
    gpu_process.join()
    disk_process.join()
