*** Settings ***
Documentation     Configurable power, CAN, relay and PID flow.
Suite Teardown    Cleanup Hardware
Resource          ../resources/power_can_basic2.resource

*** Test Cases ***
Power Can Relay Config Flow
    Run Power Can Relay Config Flow
