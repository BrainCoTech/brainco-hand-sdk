# data_reader.py
import asyncio
import time
import os
import csv
from collections import deque
import numpy as np

def save_csv(data, csv_path, csv_name, header):
    if not os.path.exists(csv_path):
        os.mkdir(csv_path)
    nf_file = open(os.path.join(csv_path, csv_name), 'w', newline='')
    nf_writer = csv.writer(nf_file)
    nf_writer.writerow(header)
    for i in range(data.shape[0]):
        data_w = data[i, :, :].flatten()
        data_w = np.insert(data_w, 0, i)
        nf_writer.writerow(data_w)
    nf_file.close()
    print("采样结束，文件已保存")

class DataReader:
    """读数据模块，异步读取触觉数据到固定长度 buffer
    in: client, slave_id, buffer_length
    """
    def __init__(self, client, slave_id, sleep_time: float, history_len: int=5):
        self.client = client
        self.slave_id = slave_id
        self.buffer = deque(maxlen=history_len)
        self.running = False
        self.finger_list = [0, 1, 2, 3, 4]
        self.force_list = [0, 1]  # 决定每个模组采集什么通道
        self.sleep_time = sleep_time

    async def start(self):
        self.running = True
        print('read_start')
        while self.running:
            try:
                _new_data = await self.parse_touch_status(self.slave_id)
                # print(_new_data)
                timestamp = time.time()
                self.buffer.append((timestamp, _new_data))
                # print(_new_data[:][:])
            except Exception as e:
                self.buffer.clear()
                print("[DataReader] Error:", e)
            await asyncio.sleep(5e-3)

    def stop(self):
        self.running = False

    def get_buffer(self):
        return list(self.buffer)

    async def parse_touch_status(self, slave_id):
        """
        如果 client.get_touch_sensor_status 返回的是复杂对象，解析为 normal list/tangential list。
        假设 touch_status[i] 有 normal_force1, tangential_force1 属性（和你原来一致）。
        """
        force_fields = ("normal_force1", "tangential_force1", "tangential_direction1", "self_proximity1")
        finger_fields = ("thumb", "index", "middle", "ring", "pinky")
        if any(finger not in range(5) for finger in self.finger_list):
            raise ValueError("Finger indices must be in 0..4.")
        if any(channel not in range(10) for channel in self.force_list):
            raise ValueError("Channel indices must be in 0..9.")

        touch_data = await self.client.get_touch_sensor_status(slave_id)
        touch_data_raw = None
        if any(channel >= len(force_fields) for channel in self.force_list):
            touch_data_raw = await self.client.get_touch_sensor_raw_data(slave_id)

        data = []
        for finger in self.finger_list:
            row = []
            for channel in self.force_list:
                if channel < len(force_fields):
                    row.append(getattr(touch_data[finger], force_fields[channel]))
                else:
                    raw_finger = getattr(touch_data_raw, finger_fields[finger])
                    row.append(raw_finger[channel - len(force_fields)])
            data.append(row)
        await asyncio.sleep(self.sleep_time)
        return data
