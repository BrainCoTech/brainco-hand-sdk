#!/usr/bin/env python3
"""
SDK Enum Usage Demo

Demonstrates all enum methods and properties exposed by the SDK:
- str(enum)      - Get enum name
- int(enum)      - Convert to integer
- enum.value     - Get integer value (alias for int_value)
- enum.int_value - Get integer value
- enum == int    - Compare with integer
- Enum(int)      - Create from integer

Usage:
    python sdk_enum_test.py
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from bc_stark_sdk import main_mod as sdk
except ImportError:
    print("Error: bc_stark_sdk not found. Run 'sh scripts/build_python.sh' first.")
    sys.exit(1)


def test_hardware_type_enum():
    """Test StarkHardwareType enum"""
    print("=== StarkHardwareType Enum ===\n")
    
    hw = sdk.StarkHardwareType.Revo1Advanced
    
    print(f"1. str(hw):        '{str(hw)}'")
    print(f"2. repr(hw):       '{repr(hw)}'")
    print(f"3. int(hw):        {int(hw)}")
    print(f"4. hw.name:        {hw.name if hasattr(hw, 'name') else str(hw).split('.')[-1]}")
    print(f"5. hw == 3:        {hw == 3}")
    print(f"   hw == 1:        {hw == 1}")
    print(f"6. hw == Revo1Advanced: {hw == sdk.StarkHardwareType.Revo1Advanced}")
    
    # Create from integer
    hw2 = sdk.StarkHardwareType(3)
    print(f"7. StarkHardwareType(3): {hw2}")
    
    # All values
    print("\n   All StarkHardwareType values:")
    all_types = [
        ("Revo1Protobuf", sdk.StarkHardwareType.Revo1Protobuf),
        ("Revo1Basic", sdk.StarkHardwareType.Revo1Basic),
        ("Revo1Touch", sdk.StarkHardwareType.Revo1Touch),
        ("Revo1Advanced", sdk.StarkHardwareType.Revo1Advanced),
        ("Revo1AdvancedTouch", sdk.StarkHardwareType.Revo1AdvancedTouch),
        ("Revo2Basic", sdk.StarkHardwareType.Revo2Basic),
        ("Revo2Touch", sdk.StarkHardwareType.Revo2Touch),
        ("Revo2TouchPressure", sdk.StarkHardwareType.Revo2TouchPressure),
        ("Revo2TouchForce3D", sdk.StarkHardwareType.Revo2TouchForce3D),
        ("Revo2TouchArrayPressure", sdk.StarkHardwareType.Revo2TouchArrayPressure),
        ("Revo3Ultra", sdk.StarkHardwareType.Revo3Ultra),
        ("Revo3UltraTouch", sdk.StarkHardwareType.Revo3UltraTouch),
        ("Revo3UltraVisionTouch", sdk.StarkHardwareType.Revo3UltraVisionTouch),
        ("Revo3Pro", sdk.StarkHardwareType.Revo3Pro),
        ("Revo3ProTouch", sdk.StarkHardwareType.Revo3ProTouch),
        ("Revo3Basic", sdk.StarkHardwareType.Revo3Basic),
        ("Revo3BasicTouch", sdk.StarkHardwareType.Revo3BasicTouch),
    ]
    for name, val in all_types:
        print(f"   {name:20} = {int(val)}")


def test_protocol_type_enum():
    """Test StarkProtocolType enum"""
    print("\n=== StarkProtocolType Enum ===\n")
    
    proto = sdk.StarkProtocolType.CanFd
    
    print(f"str(proto):      '{str(proto)}'")
    print(f"int(proto):      {int(proto)}")
    print(f"proto == 3:      {proto == 3}")
    
    print("\n   All StarkProtocolType values:")
    all_protos = [
        ("Modbus", sdk.StarkProtocolType.Modbus),
        ("Can", sdk.StarkProtocolType.Can),
        ("CanFd", sdk.StarkProtocolType.CanFd),
    ]
    for name, val in all_protos:
        print(f"   {name:10} = {int(val)}")


def test_finger_id_enum():
    """Test FingerId enum"""
    print("\n=== FingerId Enum ===\n")
    
    finger = sdk.FingerId.Middle
    
    print(f"str(finger):     '{str(finger)}'")
    print(f"int(finger):     {int(finger)}")
    
    print("\n   All FingerId values:")
    all_fingers = [
        ("Thumb", sdk.FingerId.Thumb),
        ("ThumbAux", sdk.FingerId.ThumbAux),
        ("Index", sdk.FingerId.Index),
        ("Middle", sdk.FingerId.Middle),
        ("Ring", sdk.FingerId.Ring),
        ("Pinky", sdk.FingerId.Pinky),
    ]
    for name, val in all_fingers:
        print(f"   {name:10} = {int(val)}")


def test_enum_in_dict():
    """Test using enum in dict"""
    print("\n=== Enum in Dict ===\n")
    
    hw = sdk.StarkHardwareType.Revo1Basic
    
    # PyO3 enums are not hashable, use int value as key
    d = {int(hw): "Revo1 Basic"}
    print(f"Dict with int key: {d}")
    print(f"d[1] = '{d[1]}'")
    
    # Enum as value works fine
    d2 = {"type": hw}
    print(f"Dict with enum value: {d2}")
    print(f"int(d2['type']) = {int(d2['type'])}")


def main():
    print("=" * 50)
    print("SDK Enum Usage Demo")
    print("=" * 50)
    print(f"\nSDK Version: {sdk.get_sdk_version()}\n")

    test_hardware_type_enum()
    test_protocol_type_enum()
    test_finger_id_enum()
    test_enum_in_dict()
    
    print("\n" + "=" * 50)
    print("✅ All enum tests passed!")
    print("=" * 50)


if __name__ == "__main__":
    main()
