*** Settings ***
Documentation     基于 Robot Framework 的电源与 CAN 基本流程验证。
Suite Teardown    Cleanup Hardware
Test Teardown     Cleanup Hardware
Library           ../libraries/HardwareLibrary.py    dry_run=${DRY_RUN}    time_scale=${TIME_SCALE}

*** Variables ***
# ${DRY_RUN}        True
${DRY_RUN}        False
${TIME_SCALE}     1.0

*** Test Cases ***
完整电源CAN流程验证
    [Documentation]    上电12V，等待60秒，2秒升到14.5V，CAN运行2分钟，停止CAN，2秒降到12V，等待90秒，断电到0V。
    Connect Power Supply Usb
    Set Power Voltage    12.0    output=on
    Wait Seconds    60
    Ramp Power Voltage    12.0    14.5    2    20
    Start Can Simulation
    Wait Seconds    120
    Stop Can Simulation
    Ramp Power Voltage    14.5    12.0    2    20
    Wait Seconds    90
    Power Off To Zero
