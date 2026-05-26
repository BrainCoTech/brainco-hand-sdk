class EMGData:
    @staticmethod
    def from_data(arr: list):
        return EMGData(arr[0], arr[1], arr[2:])

    def __init__(self, seq_num, lead_off_bits, channel_values):
        self.seq_num = int(seq_num)
        self.lead_off_bits = int(lead_off_bits) # Lead-off status of 8 channels
        self.channel_values = channel_values  # 8 * 20, 8 channels, each with 20 data points

    def __repr__(self):
        shape_str = f"8ch x {len(self.channel_values)//8}"
        return f"EMG seq_num={self.seq_num}, lead_off_bits={self.lead_off_bits}, shape={shape_str}, values={self.channel_values[:8]}"

class FlexData:
    @staticmethod
    def from_data(arr: list):
        return FlexData(arr[0], arr[1:])

    def __init__(self, seq_num, channel_values):
        self.seq_num = int(seq_num)
        self.channel_values = channel_values  # 6 channels

    def __repr__(self):
        shape_str = f"6ch x {len(self.channel_values)//6}"
        return f"FlexData seq_num={self.seq_num}, shape={shape_str}"

class IMUCord:

    def __init__(self, cord_x, cord_y, cord_z):
        self.cord_x = cord_x
        self.cord_y = cord_y
        self.cord_z = cord_z

    @staticmethod
    def from_json(json_obj):
        return IMUCord(
            json_obj["cordX"],
            json_obj["cordY"],
            json_obj["cordZ"],
        )

    def __repr__(self):
        return f"(x={self.cord_x}, y={self.cord_y}, z={self.cord_z})"


class IMUData:
    @staticmethod
    def from_data(arr: list):
        # Ensure arr has at least 7 elements, pad with 0.0 if not enough to prevent IndexError
        extended = arr + [0.0] * max(0, 7 - len(arr))
        return IMUData(extended[0], extended[1:4], extended[4:7])

    def __init__(self, seqnum, acc, gyro):
        self.seqnum = int(seqnum) & 0xFFFF
        self.acc = IMUCord(acc[0], acc[1], acc[2])
        self.gyro = IMUCord(gyro[0], gyro[1], gyro[2])

    def __repr__(self):
        return f"IMU seqnum={self.seqnum}, acc={self.acc}, gyro={self.gyro}"


class MagData:
    @staticmethod
    def from_data(arr: list):
        # Ensure arr has at least 4 elements, pad with 0.0 if not enough to prevent IndexError
        extended = arr + [0.0] * max(0, 4 - len(arr))
        return MagData(extended[0], extended[1:4])

    def __init__(self, seqnum, acc):
        self.seqnum = int(seqnum) & 0xFFFF
        self.data = IMUCord(acc[0], acc[1], acc[2])

    def __repr__(self):
        return f"MAG seqnum={self.seqnum}, data={self.data}"


class EulerData:
    @staticmethod
    def from_data(arr: list):
        # Ensure arr has at least 4 elements, pad with 0.0 if not enough to prevent IndexError
        extended = arr + [0.0] * max(0, 4 - len(arr))
        return EulerData(extended[0], extended[1:4])

    def __init__(self, seqnum, euler):
        self.seqnum = int(seqnum) & 0xFFFF
        self.yaw = euler[0]
        self.pitch = euler[1]
        self.roll = euler[2]

    def __repr__(self):
        return f"Euler seqnum={self.seqnum}, yaw={self.yaw:.2f}, pitch={self.pitch:.2f}, roll={self.roll:.2f}"

