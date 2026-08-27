*** Settings ***
Documentation     Basic3 flow: power reset, relay, CAN dynamic simulation, shutdown.
Suite Teardown    Cleanup Hardware
Resource          ../resources/power_can_basic3.resource

*** Test Cases ***
Power Can Basic3 Dynamic Flow
    Run Power Can Basic3 Flow

Power Can Basic3 Dynamic Flow Full Steps
    Configure Runtime    ${DRY_RUN}    ${TIME_SCALE}
    Power Connect And Reset To Zero
    Power On And Ramp To High
    Relay Connect And Turn On
    Can Configure Default Dynamic Profile
    Start Can Simulation
    Wait Seconds    ${CAN_RUN_SECONDS}
    Power Ramp Back To Normal
    Stop Can Simulation
    Close Can Connection
    Relay Turn Off And Disconnect
    Power Wait Off And Disconnect

Power Can Basic3 Dynamic Flow Plus
    Configure Runtime    ${DRY_RUN}    ${TIME_SCALE}
    Connect Power Supply Usb
    Power Off To Zero
    Wait Seconds    ${POWER_PRE_ON_DELAY_SECONDS}
    Set Power Current    ${POWER_CURRENT_A}
    Set Power Voltage    0    on
    Ramp Power Voltage    0    ${POWER_ON_VOLTAGE}    ${POWER_0_TO_12_SECONDS}    ${POWER_RAMP_STEPS}
    Wait Seconds    ${POWER_ON_WAIT_SECONDS}
    Ramp Power Voltage    ${POWER_ON_VOLTAGE}    ${POWER_HIGH_VOLTAGE}    ${POWER_RAMP_SECONDS}    ${POWER_RAMP_STEPS}
    Connect Relay Usb
    Set Relay Channel    ${RELAY_CHANNEL}    ${RELAY_ON_STATE}
    Configure Can Simulation    ${CAN_ID_FORMAT}    ${CAN_BITRATE}    ${CAN_CHANNEL_INDEX}
    Set Can Signal Range    speed    ${CAN_DEFAULT_SPEED_MIN}    ${CAN_DEFAULT_SPEED_MAX}
    Set Can Signal Range    rpm    ${CAN_DEFAULT_RPM_MIN}    ${CAN_DEFAULT_RPM_MAX}
    Set Can Signal Range    A    80    90
    Set Can Signal Range    B    0    100
    Set Can Signal Range    C    0    100
    Set Can Signal Range    D    0    10
    Set Can Signal Range    E    -40    100
    Set Can Signal Range    F    0    255
    Set Can Signal Range    G    11    15.5
    Set Can Signal Range    H    0    100
    Set Can Signal Range    I    0    1000
    Set Can Signal Range    J    0    1000
    Set Can Signal Range    M    0    100000
    Set Can Signal Range    N    0    20000
    Set Can Signal Range    O    1    2
    Set Can Signal Range    P    0    100
    Set Can Signal Range    Q    0    100
    Set Can Signal Range    R    -500    500
    Set Can Signal Range    S    0    1000
    Set Can Signal Range    T    0    3
    Set Can Signal Range    U    0    1000
    Set Can Signal Range    V    -40    100
    Set Can Signal Range    W    0    50000
    Set Can Signal Range    X    0    100000
    Set Can Signal Range    Y    0    32
    Set Can Signal Range    Z    0    3
    Start Can Simulation
    Wait Seconds    ${CAN_RUN_SECONDS}
    Ramp Power Voltage    ${POWER_HIGH_VOLTAGE}    ${POWER_ON_VOLTAGE}    ${POWER_RAMP_SECONDS}    ${POWER_RAMP_STEPS}
    Stop Can Simulation
    Close Can Connection
    Set Relay Channel    ${RELAY_CHANNEL}    ${RELAY_OFF_STATE}
    Close Relay Usb
    Wait Seconds    ${POWER_END_WAIT_SECONDS}
    Power Off To Zero
    Close Power Supply Usb

Power Can Basic3 Dynamic Flow Plus Clear
    Configure Runtime    false    1.0
    Connect Power Supply Usb
    Power Off To Zero
    Wait Seconds    3
    Set Power Current    2.0
    Set Power Voltage    0    on
    Ramp Power Voltage    0    12.0    2    20
    Wait Seconds    60
    Ramp Power Voltage    12.0    15.0    5    20
    Connect Relay Usb
    Set Relay Channel    1    close
    Configure Can Simulation    11bit    500000    0
    Set Can Signal Range    speed    0    120
    Set Can Signal Range    rpm    1000    3000
    Set Can Signal Range    A    80    90
    Set Can Signal Range    B    0    100
    Set Can Signal Range    C    0    100
    Set Can Signal Range    D    0    10
    Set Can Signal Range    E    -40    100
    Set Can Signal Range    F    0    255
    Set Can Signal Range    G    11    15.5
    Set Can Signal Range    H    0    100
    Set Can Signal Range    I    0    1000
    Set Can Signal Range    J    0    1000
    Set Can Signal Range    M    0    100000
    Set Can Signal Range    N    0    20000
    Set Can Signal Range    O    1    2
    Set Can Signal Range    P    0    100
    Set Can Signal Range    Q    0    100
    Set Can Signal Range    R    -500    500
    Set Can Signal Range    S    0    1000
    Set Can Signal Range    T    0    3
    Set Can Signal Range    U    0    1000
    Set Can Signal Range    V    -40    100
    Set Can Signal Range    W    0    50000
    Set Can Signal Range    X    0    100000
    Set Can Signal Range    Y    0    32
    Set Can Signal Range    Z    0    3
    Start Can Simulation
    Wait Seconds    120
    Ramp Power Voltage    15.0    12.0    5    20
    Stop Can Simulation
    Close Can Connection
    Set Relay Channel    1    open
    Close Relay Usb
    Wait Seconds    90
    Power Off To Zero
    Close Power Supply Usb

Power Can Basic3 Fixed Values 11bit 500K
    Configure Runtime    false    1.0
    Connect Power Supply Usb
    Power Off To Zero
    Wait Seconds    3
    Set Power Current    2.0
    Set Power Voltage    0    on
    Ramp Power Voltage    0    12.0    2    20
    Wait Seconds    60
    Ramp Power Voltage    12.0    15.0    5    20
    Connect Relay Usb
    Set Relay Channel    1    close
    Configure Can Simulation    11bit    500000    0
    Set Wwh Obd Current Dtc    set    0101    0202    0103    0102
    Set Can Signal Range    speed    60    125
    Set Can Signal Range    rpm    2000    2010
    Set Can Signal Value    A    85
    Set Can Signal Value    B    92.9
    Set Can Signal Value    C    5.8
    Set Can Signal Value    D    0.1
    Set Can Signal Value    E    -23
    Set Can Signal Value    F    17
    Set Can Signal Value    G    14.9
    Set Can Signal Value    H    60
    Set Can Signal Value    I    17
    Set Can Signal Value    J    17
    Set Can Signal Value    K1    123456
    Set Can Signal Value    K2    6543
    Set Can Signal Value    K3    789
    Set Can Signal Value    L    1
    Set Can Signal Value    M    12345
    Set Can Signal Value    N    88
    Set Can Signal Value    O    1
    Set Can Signal Value    P    93.3
    Set Can Signal Value    Q    93
    Set Can Signal Value    R    12
    Set Can Signal Value    S    360
    Set Can Signal Value    T    1
    Set Can Signal Value    U    456
    Set Can Signal Value    V    25
    Set Can Signal Value    W    5000
    Set Can Signal Value    X    17
    Set Can Signal Value    Y    1
    Set Can Signal Value    Z    1
    Start Can Simulation
    Wait Seconds    ${CAN_RUN_SECONDS}
    Ramp Power Voltage    15.0    12.0    5    20
    Stop Can Simulation
    Close Can Connection
    Set Relay Channel    1    open
    Close Relay Usb
    Wait Seconds    90
    Power Off To Zero
    Close Power Supply Usb

Power Can Basic3 Fixed Values 11bit 250K
    Configure Runtime    false    1.0
    Connect Power Supply Usb
    Power Off To Zero
    Wait Seconds    3
    Set Power Current    2.0
    Set Power Voltage    0    on
    Ramp Power Voltage    0    12.0    2    20
    Wait Seconds    60
    Ramp Power Voltage    12.0    15.0    5    20
    Connect Relay Usb
    Set Relay Channel    1    close
    Configure Can Simulation    11bit    250000    0
    Set Wwh Obd Current Dtc    set    0101    0202    0103    0102
    Set Can Signal Range    speed    60    125
    Set Can Signal Range    rpm    2000    2010
    Set Can Signal Value    A    85
    Set Can Signal Value    B    92.9
    Set Can Signal Value    C    5.8
    Set Can Signal Value    D    0.1
    Set Can Signal Value    E    -23
    Set Can Signal Value    F    17
    Set Can Signal Value    G    14.9
    Set Can Signal Value    H    60
    Set Can Signal Value    I    17
    Set Can Signal Value    J    17
    Set Can Signal Value    K1    123456
    Set Can Signal Value    K2    6543
    Set Can Signal Value    K3    789
    Set Can Signal Value    L    1
    Set Can Signal Value    M    12345
    Set Can Signal Value    N    88
    Set Can Signal Value    O    1
    Set Can Signal Value    P    93.3
    Set Can Signal Value    Q    93
    Set Can Signal Value    R    12
    Set Can Signal Value    S    360
    Set Can Signal Value    T    1
    Set Can Signal Value    U    456
    Set Can Signal Value    V    25
    Set Can Signal Value    W    5000
    Set Can Signal Value    X    17
    Set Can Signal Value    Y    1
    Set Can Signal Value    Z    1
    Start Can Simulation
    Wait Seconds    120
    Ramp Power Voltage    15.0    12.0    5    20
    Stop Can Simulation
    Close Can Connection
    Set Relay Channel    1    open
    Close Relay Usb
    Wait Seconds    90
    Power Off To Zero
    Close Power Supply Usb

Power Can Basic3 Fixed Values 29bit 500K
    Configure Runtime    false    1.0
    Connect Power Supply Usb
    Power Off To Zero
    Wait Seconds    3
    Set Power Current    2.0
    Set Power Voltage    0    on
    Ramp Power Voltage    0    12.0    2    20
    Wait Seconds    60
    Ramp Power Voltage    12.0    15.0    5    20
    Connect Relay Usb
    Set Relay Channel    1    close
    Configure Can Simulation    29bit    500000    0
    Set Wwh Obd Current Dtc    set    0101    0202    0103    0102
    Set Can Signal Range    speed    60    125
    Set Can Signal Range    rpm    2000    2010
    Set Can Signal Value    A    85
    Set Can Signal Value    B    92.9
    Set Can Signal Value    C    5.8
    Set Can Signal Value    D    0.1
    Set Can Signal Value    E    -23
    Set Can Signal Value    F    17
    Set Can Signal Value    G    14.9
    Set Can Signal Value    H    60
    Set Can Signal Value    I    17
    Set Can Signal Value    J    17
    Set Can Signal Value    K1    123456
    Set Can Signal Value    K2    6543
    Set Can Signal Value    K3    789
    Set Can Signal Value    L    1
    Set Can Signal Value    M    12345
    Set Can Signal Value    N    88
    Set Can Signal Value    O    1
    Set Can Signal Value    P    93.3
    Set Can Signal Value    Q    93
    Set Can Signal Value    R    12
    Set Can Signal Value    S    360
    Set Can Signal Value    T    1
    Set Can Signal Value    U    456
    Set Can Signal Value    V    25
    Set Can Signal Value    W    5000
    Set Can Signal Value    X    17
    Set Can Signal Value    Y    1
    Set Can Signal Value    Z    1
    Start Can Simulation
    Wait Seconds    120
    Ramp Power Voltage    15.0    12.0    5    20
    Stop Can Simulation
    Close Can Connection
    Set Relay Channel    1    open
    Close Relay Usb
    Wait Seconds    90
    Power Off To Zero
    Close Power Supply Usb

Power Can Basic3 Fixed Values 29bit 250K
    Configure Runtime    false    1.0
    Connect Power Supply Usb
    Power Off To Zero
    Wait Seconds    3
    Set Power Current    2.0
    Set Power Voltage    0    on
    Ramp Power Voltage    0    12.0    2    20
    Wait Seconds    60
    Ramp Power Voltage    12.0    15.0    5    20
    Connect Relay Usb
    Set Relay Channel    1    close
    Configure Can Simulation    29bit    250000    0
    Set Wwh Obd Current Dtc    set    0101    0202    0103    0102
    Set Can Signal Range    speed    60    125
    Set Can Signal Range    rpm    2000    2010
    Set Can Signal Value    A    85
    Set Can Signal Value    B    92.9
    Set Can Signal Value    C    5.8
    Set Can Signal Value    D    0.1
    Set Can Signal Value    E    -23
    Set Can Signal Value    F    17
    Set Can Signal Value    G    14.9
    Set Can Signal Value    H    60
    Set Can Signal Value    I    17
    Set Can Signal Value    J    17
    Set Can Signal Value    K1    123456
    Set Can Signal Value    K2    6543
    Set Can Signal Value    K3    789
    Set Can Signal Value    L    1
    Set Can Signal Value    M    12345
    Set Can Signal Value    N    88
    Set Can Signal Value    O    1
    Set Can Signal Value    P    93.3
    Set Can Signal Value    Q    93
    Set Can Signal Value    R    12
    Set Can Signal Value    S    360
    Set Can Signal Value    T    1
    Set Can Signal Value    U    456
    Set Can Signal Value    V    25
    Set Can Signal Value    W    5000
    Set Can Signal Value    X    17
    Set Can Signal Value    Y    1
    Set Can Signal Value    Z    1
    Start Can Simulation
    Wait Seconds    120
    Ramp Power Voltage    15.0    12.0    5    20
    Stop Can Simulation
    Close Can Connection
    Set Relay Channel    1    open
    Close Relay Usb
    Wait Seconds    90
    Power Off To Zero
    Close Power Supply Usb
