package com.bianyi.bleat;

import android.Manifest;
import android.app.Activity;
import android.app.AlertDialog;
import android.bluetooth.BluetoothAdapter;
import android.bluetooth.BluetoothDevice;
import android.bluetooth.BluetoothGatt;
import android.bluetooth.BluetoothGattCallback;
import android.bluetooth.BluetoothGattCharacteristic;
import android.bluetooth.BluetoothGattDescriptor;
import android.bluetooth.BluetoothGattService;
import android.bluetooth.BluetoothManager;
import android.bluetooth.BluetoothProfile;
import android.bluetooth.BluetoothStatusCodes;
import android.bluetooth.le.BluetoothLeScanner;
import android.bluetooth.le.ScanCallback;
import android.bluetooth.le.ScanResult;
import android.bluetooth.le.ScanSettings;
import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.content.IntentFilter;
import android.content.pm.PackageManager;
import android.graphics.Color;
import android.graphics.Typeface;
import android.graphics.drawable.ColorDrawable;
import android.graphics.drawable.GradientDrawable;
import android.os.Build;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.location.LocationManager;
import android.net.Uri;
import android.provider.Settings;
import android.text.Editable;
import android.text.InputType;
import android.text.TextWatcher;
import android.view.Gravity;
import android.view.MotionEvent;
import android.view.View;
import android.view.ViewGroup;
import android.view.Window;
import android.view.WindowManager;
import android.widget.ArrayAdapter;
import android.widget.BaseAdapter;
import android.widget.Button;
import android.widget.EditText;
import android.widget.FrameLayout;
import android.widget.LinearLayout;
import android.widget.ListView;
import android.widget.ScrollView;
import android.widget.Spinner;
import android.widget.Switch;
import android.widget.TextView;
import android.widget.Toast;

import java.nio.charset.StandardCharsets;
import java.text.SimpleDateFormat;
import java.util.ArrayList;
import java.util.Date;
import java.util.HashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.UUID;

public class MainActivity extends Activity {
    private static final int COLOR_BACKGROUND = 0xFFFFFFFF;
    private static final int COLOR_CARD = 0xFFF4F7FA;
    private static final int COLOR_TEXT = 0xFF172033;
    private static final int COLOR_TEXT_SECONDARY = 0xFF65748A;
    private static final int COLOR_TEAL = 0xFF087F72;
    private static final int COLOR_BORDER = 0xFFD5DDE8;
    private static final int REQUEST_BLE_PERMISSIONS = 101;
    private static final long SCAN_DURATION_MS = 20_000L;
    private static final long DEVICE_LIST_REFRESH_INTERVAL_MS = 220L;
    private static final UUID CCCD_UUID = UUID.fromString("00002902-0000-1000-8000-00805f9b34fb");
    private static final String UART_TX_UUID = "0000ffe1";
    private static final String NORDIC_WRITE_UUID = "6e400002";
    private static final String NORDIC_NOTIFY_UUID = "6e400003";
    private static final String CONFIG_SERVICE_UUID = "d973f2e0-b19e-11e2-9e96-0800200c9a66";
    private static final String CONFIG_TX_UUID = "d973f2e1-b19e-11e2-9e96-0800200c9a66";
    private static final String CONFIG_RX_UUID = "d973f2e2-b19e-11e2-9e96-0800200c9a66";

    private final Handler handler = new Handler(Looper.getMainLooper());
    private final List<BluetoothDevice> devices = new ArrayList<>();
    private final List<String> deviceNames = new ArrayList<>();
    private final List<String> deviceAddresses = new ArrayList<>();
    private final List<String> deviceRows = new ArrayList<>();
    private final Map<String, Integer> deviceIndexByAddress = new HashMap<>();
    private final List<Integer> filteredDeviceIndices = new ArrayList<>();
    private final List<ServiceEntry> services = new ArrayList<>();
    private final List<CharacteristicEntry> writeOptions = new ArrayList<>();
    private final List<CharacteristicEntry> notifyOptions = new ArrayList<>();

    private BluetoothAdapter bluetoothAdapter;
    private BluetoothLeScanner scanner;
    private BluetoothGatt bluetoothGatt;
    private BluetoothDevice selectedDevice;
    private boolean scanning;
    private boolean connected;
    private boolean connecting;
    private boolean updatingCharacteristicSpinners;
    private boolean waitingForLocationEnable;
    private boolean bondReceiverRegistered;
    private boolean communicationServiceOpen;
    private boolean txChannelOpen;
    private boolean rxChannelOpen;
    private boolean notificationChangePending;
    private boolean requestedNotificationsEnabled;
    private boolean notificationsEnabled;
    private BluetoothGattCharacteristic notificationCharacteristic;
    private boolean updatingCommunicationSwitch;
    private boolean updatingChannelSwitches;
    private boolean deviceListBeingTouched;
    private boolean deviceListRefreshScheduled;

    private LinearLayout root;
    private FrameLayout screenContainer;
    private View mainPage;
    private View workspacePage;
    private View servicePage;
    private View atPage;
    private View activationStatusRow;
    private ListView deviceListView;
    private BaseAdapter deviceListAdapter;
    private TextView statusView;
    private TextView selectedDeviceView;
    private TextView connectedDeviceHeader;
    private TextView connectedStatusHeader;
    private TextView discoveredServicesView;
    private TextView communicationStatusView;
    private TextView txChannelStatusView;
    private TextView rxChannelStatusView;
    private TextView atChannelStatusView;
    private TextView logView;
    private ScrollView logScroll;
    private Button scanButton;
    private Button connectButton;
    private Button pairButton;
    private Button sendButton;
    private Switch communicationServiceSwitch;
    private Switch txChannelSwitch;
    private Switch rxChannelSwitch;
    private Button readButton;
    private Button serviceTabButton;
    private Button atTabButton;
    private Spinner serviceSpinner;
    private Spinner writeSpinner;
    private Spinner notifySpinner;
    private Spinner suffixSpinner;
    private Spinner commandPresetSpinner;
    private EditText nameFilterInput;
    private EditText macFilterInput;
    private EditText commandInput;
    private TextView activationStatusView;
    private String pendingActivationCommand = "";
    private final StringBuilder activationResponseBuffer = new StringBuilder();
    private byte[] pendingWritePayload = new byte[0];
    private BluetoothGattCharacteristic pendingWriteCharacteristic;
    private boolean writeFallbackAttempted;
    private int negotiatedMtu = 23;
    private final List<byte[]> writeChunks = new ArrayList<>();
    private int writeChunkIndex;
    private int writeSequenceGeneration;
    private boolean writeSequenceActive;
    private BluetoothGattCharacteristic activeWriteCharacteristic;
    private String activeCommandDisplay = "";
    private BluetoothDevice pendingAutoConnectDevice;

    private final Runnable stopScanRunnable = () -> stopScan("扫描结束");
    private final Runnable deviceListRefreshRunnable = () -> {
        deviceListRefreshScheduled = false;
        if (deviceListBeingTouched) {
            scheduleDeviceListRefresh(DEVICE_LIST_REFRESH_INTERVAL_MS, false);
            return;
        }
        renderDevices();
        if (scanning) {
            setStatus(scanProgressText());
        } else if (!connected && !devices.isEmpty()) {
            setStatus("过滤后显示 " + filteredDeviceIndices.size() + " / " + devices.size() + " 台设备");
        }
    };
    private final BroadcastReceiver bondStateReceiver = new BroadcastReceiver() {
        @Override
        public void onReceive(Context context, Intent intent) {
            if (!BluetoothDevice.ACTION_BOND_STATE_CHANGED.equals(intent.getAction())) return;
            BluetoothDevice device = intent.getParcelableExtra(BluetoothDevice.EXTRA_DEVICE);
            if (device == null) return;
            int state = intent.getIntExtra(BluetoothDevice.EXTRA_BOND_STATE, BluetoothDevice.BOND_NONE);
            String address = safeAddress(device);
            renderDevices();
            if (selectedDevice != null && safeAddress(selectedDevice).equalsIgnoreCase(address)) {
                if (state == BluetoothDevice.BOND_BONDED) {
                    setStatus("配对成功 · 可以连接设备");
                    appendLog("[配对] " + address + " 已配对\n");
                    updateSelectedDeviceLabel();
                } else if (state == BluetoothDevice.BOND_BONDING) {
                    setStatus("正在与 " + address + " 配对…");
                } else {
                    setStatus("设备未配对 · 仍可尝试 BLE 连接");
                    appendLog("[配对] " + address + " 未配对或配对已取消\n");
                    updateSelectedDeviceLabel();
                }
                updatePairButton();
            }
        }
    };

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        Window window = getWindow();
        window.setStatusBarColor(Color.WHITE);
        window.setNavigationBarColor(Color.WHITE);
        int systemUiFlags = View.SYSTEM_UI_FLAG_LIGHT_STATUS_BAR;
        if (Build.VERSION.SDK_INT >= 26) systemUiFlags |= View.SYSTEM_UI_FLAG_LIGHT_NAVIGATION_BAR;
        window.getDecorView().setSystemUiVisibility(systemUiFlags);
        window.setSoftInputMode(WindowManager.LayoutParams.SOFT_INPUT_ADJUST_RESIZE);
        buildInterface();
        registerBondStateReceiver();

        BluetoothManager manager = (BluetoothManager) getSystemService(Context.BLUETOOTH_SERVICE);
        bluetoothAdapter = manager == null ? null : manager.getAdapter();
        if (bluetoothAdapter == null) {
            setStatus("此设备没有可用的蓝牙适配器");
            scanButton.setEnabled(false);
            connectButton.setEnabled(false);
            return;
        }
        setStatus("未连接 · 先扫描并选择 BLE 设备");
    }

    private void buildInterface() {
        ScrollView page = new ScrollView(this);
        page.setFillViewport(true);
        page.setBackgroundColor(COLOR_BACKGROUND);
        mainPage = page;

        root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        root.setPadding(dp(18), dp(20), dp(18), dp(28));
        page.addView(root, new ScrollView.LayoutParams(-1, -2));

        TextView title = text("BLE AT 调试助手 - GNN", 25, COLOR_TEXT, true);
        root.addView(title);
        TextView subtitle = text("低功耗蓝牙连接 · AT 命令收发", 14, COLOR_TEXT_SECONDARY, false);
        LinearLayout.LayoutParams subtitleParams = new LinearLayout.LayoutParams(-1, -2);
        subtitleParams.topMargin = dp(5);
        subtitleParams.bottomMargin = dp(18);
        root.addView(subtitle, subtitleParams);

        LinearLayout connectionCard = section("连接设备");
        root.addView(connectionCard, sectionParams());
        statusView = text("正在初始化蓝牙…", 14, COLOR_TEAL, true);
        connectionCard.addView(statusView);
        LinearLayout actionRow = horizontal();
        scanButton = button("扫描 BLE", 0xFF1E3A52);
        connectButton = button("连接所选设备", 0xFF087F72);
        pairButton = button("配对", 0xFF596780);
        connectButton.setEnabled(false);
        pairButton.setEnabled(false);
        actionRow.addView(scanButton, weightParams(0.85f, 0, dp(6)));
        actionRow.addView(connectButton, weightParams(1.25f, 0, dp(6)));
        actionRow.addView(pairButton, weightParams(0.75f, 0, 0));
        LinearLayout.LayoutParams actionParams = new LinearLayout.LayoutParams(-1, -2);
        actionParams.topMargin = dp(12);
        connectionCard.addView(actionRow, actionParams);

        TextView filterLabel = text("扫描结果过滤（留空表示不过滤）", 13, COLOR_TEXT_SECONDARY, false);
        LinearLayout.LayoutParams filterLabelParams = new LinearLayout.LayoutParams(-1, -2);
        filterLabelParams.topMargin = dp(14);
        connectionCard.addView(filterLabel, filterLabelParams);
        nameFilterInput = filterInput("设备名称包含，例如：BT05");
        connectionCard.addView(nameFilterInput, compactFieldParams());
        macFilterInput = filterInput("MAC 包含，例如：A4:C1 或 A4C1");
        connectionCard.addView(macFilterInput, compactFieldParams());
        TextWatcher filterWatcher = new TextWatcher() {
            @Override public void beforeTextChanged(CharSequence s, int start, int count, int after) { }
            @Override public void onTextChanged(CharSequence s, int start, int before, int count) { }
            @Override public void afterTextChanged(Editable s) { onDeviceFilterChanged(); }
        };
        nameFilterInput.addTextChangedListener(filterWatcher);
        macFilterInput.addTextChangedListener(filterWatcher);

        TextView deviceLabel = text("发现的设备（点选一台）", 13, COLOR_TEXT_SECONDARY, false);
        LinearLayout.LayoutParams deviceLabelParams = new LinearLayout.LayoutParams(-1, -2);
        deviceLabelParams.topMargin = dp(8);
        connectionCard.addView(deviceLabel, deviceLabelParams);
        deviceListView = new ListView(this);
        deviceListView.setVerticalScrollBarEnabled(true);
        deviceListView.setNestedScrollingEnabled(true);
        deviceListView.setBackground(rounded(Color.WHITE, dp(10)));
        deviceListView.setDivider(new ColorDrawable(Color.TRANSPARENT));
        deviceListView.setDividerHeight(dp(4));
        deviceListView.setSelector(android.R.color.transparent);
        deviceListView.setPadding(dp(5), dp(3), dp(5), dp(5));
        deviceListView.setClipToPadding(false);
        deviceListAdapter = new DeviceListAdapter();
        deviceListView.setAdapter(deviceListAdapter);
        deviceListView.setOnItemClickListener((parent, view, position, id) -> {
            if (position >= 0 && position < filteredDeviceIndices.size()) {
                handleDeviceTap(filteredDeviceIndices.get(position));
            }
        });
        deviceListView.setOnTouchListener((view, event) -> {
            if (event.getAction() == MotionEvent.ACTION_DOWN || event.getAction() == MotionEvent.ACTION_MOVE) {
                deviceListBeingTouched = true;
                view.getParent().requestDisallowInterceptTouchEvent(true);
            } else if (event.getAction() == MotionEvent.ACTION_UP || event.getAction() == MotionEvent.ACTION_CANCEL) {
                deviceListBeingTouched = false;
                view.getParent().requestDisallowInterceptTouchEvent(false);
                scheduleDeviceListRefresh(0, true);
            }
            return false;
        });
        connectionCard.addView(deviceListView, new LinearLayout.LayoutParams(-1, dp(52)));

        selectedDeviceView = text("当前选择：无", 12, COLOR_TEXT_SECONDARY, false);
        LinearLayout.LayoutParams selectedParams = new LinearLayout.LayoutParams(-1, -2);
        selectedParams.topMargin = dp(10);
        connectionCard.addView(selectedDeviceView, selectedParams);

        LinearLayout workspaceRoot = new LinearLayout(this);
        workspaceRoot.setOrientation(LinearLayout.VERTICAL);
        workspaceRoot.setBackgroundColor(COLOR_BACKGROUND);
        workspacePage = workspaceRoot;

        LinearLayout workspaceHeader = new LinearLayout(this);
        workspaceHeader.setOrientation(LinearLayout.VERTICAL);
        workspaceHeader.setPadding(dp(18), dp(14), dp(18), dp(12));
        workspaceHeader.setBackground(rounded(0xFFF0F6F8, 0));
        Button backButton = button("← BLE 列表", 0xFFE2E9F0);
        backButton.setTextColor(COLOR_TEXT);
        workspaceHeader.addView(backButton, new LinearLayout.LayoutParams(-2, dp(38)));
        connectedDeviceHeader = text("尚未连接 BLE 设备", 18, COLOR_TEXT, true);
        LinearLayout.LayoutParams deviceHeaderParams = new LinearLayout.LayoutParams(-1, -2);
        deviceHeaderParams.topMargin = dp(8);
        workspaceHeader.addView(connectedDeviceHeader, deviceHeaderParams);
        connectedStatusHeader = text("未连接", 13, 0xFFC62828, true);
        LinearLayout.LayoutParams statusHeaderParams = new LinearLayout.LayoutParams(-1, -2);
        statusHeaderParams.topMargin = dp(3);
        workspaceHeader.addView(connectedStatusHeader, statusHeaderParams);
        workspaceRoot.addView(workspaceHeader, new LinearLayout.LayoutParams(-1, -2));

        LinearLayout tabRow = horizontal();
        tabRow.setPadding(dp(18), dp(10), dp(18), dp(10));
        serviceTabButton = button("服务", COLOR_TEAL);
        atTabButton = button("AT", 0xFFE2E9F0);
        atTabButton.setTextColor(COLOR_TEXT);
        tabRow.addView(serviceTabButton, weightParams(1, 0, dp(8)));
        tabRow.addView(atTabButton, weightParams(1, 0, 0));
        workspaceRoot.addView(tabRow, new LinearLayout.LayoutParams(-1, -2));

        FrameLayout workspaceContent = new FrameLayout(this);
        ScrollView serviceScroll = new ScrollView(this);
        serviceScroll.setFillViewport(true);
        LinearLayout serviceRoot = new LinearLayout(this);
        serviceRoot.setOrientation(LinearLayout.VERTICAL);
        serviceRoot.setPadding(dp(18), dp(4), dp(18), dp(24));
        serviceScroll.addView(serviceRoot, new ScrollView.LayoutParams(-1, -2));
        servicePage = serviceScroll;

        ScrollView atScroll = new ScrollView(this);
        atScroll.setFillViewport(true);
        LinearLayout atRoot = new LinearLayout(this);
        atRoot.setOrientation(LinearLayout.VERTICAL);
        atRoot.setPadding(dp(18), dp(4), dp(18), dp(24));
        atScroll.addView(atRoot, new ScrollView.LayoutParams(-1, -2));
        atPage = atScroll;
        atPage.setVisibility(View.GONE);
        workspaceContent.addView(servicePage, new FrameLayout.LayoutParams(-1, -1));
        workspaceContent.addView(atPage, new FrameLayout.LayoutParams(-1, -1));
        workspaceRoot.addView(workspaceContent, new LinearLayout.LayoutParams(-1, 0, 1));

        backButton.setOnClickListener(v -> showMainScreen());
        serviceTabButton.setOnClickListener(v -> showServiceTab());
        atTabButton.setOnClickListener(v -> showAtTab());

        LinearLayout gattCard = section("BLE 服务与特征值");
        serviceRoot.addView(gattCard, sectionParams());
        gattCard.addView(text("私有配置服务", 14, COLOR_TEXT, true));
        gattCard.addView(text(CONFIG_SERVICE_UUID, 11, COLOR_TEXT_SECONDARY, false));
        // 下拉框仅作为内部 GATT 状态容器，不再显示给用户。
        serviceSpinner = spinner();
        writeSpinner = spinner();
        notifySpinner = spinner();

        LinearLayout serviceActionRow = horizontal();
        communicationStatusView = text("配置服务：关闭", 13, COLOR_TEXT_SECONDARY, true);
        serviceActionRow.addView(communicationStatusView, new LinearLayout.LayoutParams(0, -2, 1));
        communicationServiceSwitch = new Switch(this);
        communicationServiceSwitch.setText("服务");
        communicationServiceSwitch.setTextColor(COLOR_TEXT);
        communicationServiceSwitch.setTextSize(13);
        communicationServiceSwitch.setShowText(true);
        communicationServiceSwitch.setTextOn("打开");
        communicationServiceSwitch.setTextOff("关闭");
        communicationServiceSwitch.setChecked(false);
        communicationServiceSwitch.setEnabled(false);
        serviceActionRow.addView(communicationServiceSwitch, new LinearLayout.LayoutParams(dp(132), dp(46)));
        serviceActionRow.setPadding(dp(8), dp(3), dp(3), dp(3));
        serviceActionRow.setBackground(rounded(0xFFEAF0F5, dp(10)));
        LinearLayout.LayoutParams serviceActionParams = new LinearLayout.LayoutParams(-1, -2);
        serviceActionParams.topMargin = dp(7);
        gattCard.addView(serviceActionRow, serviceActionParams);

        LinearLayout txActionRow = horizontal();
        txChannelStatusView = text("TX 发送：关闭\n" + CONFIG_TX_UUID, 12, COLOR_TEXT_SECONDARY, false);
        txActionRow.addView(txChannelStatusView, new LinearLayout.LayoutParams(0, -2, 1));
        txChannelSwitch = new Switch(this);
        txChannelSwitch.setText("TX");
        txChannelSwitch.setTextColor(COLOR_TEXT);
        txChannelSwitch.setShowText(true);
        txChannelSwitch.setTextOn("打开");
        txChannelSwitch.setTextOff("关闭");
        txChannelSwitch.setChecked(false);
        txChannelSwitch.setEnabled(false);
        txActionRow.addView(txChannelSwitch, new LinearLayout.LayoutParams(dp(132), dp(50)));
        txActionRow.setPadding(dp(8), dp(3), dp(3), dp(3));
        txActionRow.setBackground(rounded(0xFFEAF0F5, dp(10)));
        LinearLayout.LayoutParams txActionParams = new LinearLayout.LayoutParams(-1, -2);
        txActionParams.topMargin = dp(10);
        gattCard.addView(txActionRow, txActionParams);

        LinearLayout rxActionRow = horizontal();
        rxChannelStatusView = text("RX 接收：关闭\n" + CONFIG_RX_UUID, 12, COLOR_TEXT_SECONDARY, false);
        rxActionRow.addView(rxChannelStatusView, new LinearLayout.LayoutParams(0, -2, 1));
        rxChannelSwitch = new Switch(this);
        rxChannelSwitch.setText("RX");
        rxChannelSwitch.setTextColor(COLOR_TEXT);
        rxChannelSwitch.setShowText(true);
        rxChannelSwitch.setTextOn("打开");
        rxChannelSwitch.setTextOff("关闭");
        rxChannelSwitch.setChecked(false);
        rxChannelSwitch.setEnabled(false);
        rxActionRow.addView(rxChannelSwitch, new LinearLayout.LayoutParams(dp(132), dp(50)));
        rxActionRow.setPadding(dp(8), dp(3), dp(3), dp(3));
        rxActionRow.setBackground(rounded(0xFFEAF0F5, dp(10)));
        LinearLayout.LayoutParams rxActionParams = new LinearLayout.LayoutParams(-1, -2);
        rxActionParams.topMargin = dp(8);
        gattCard.addView(rxActionRow, rxActionParams);

        readButton = button("读取接收特征值", 0xFF2878B5);
        readButton.setEnabled(false);

        LinearLayout publicServicesCard = section("标准与公开服务");
        discoveredServicesView = text("连接设备后显示已发现的标准服务。", 12, COLOR_TEXT_SECONDARY, false);
        discoveredServicesView.setTextIsSelectable(true);
        discoveredServicesView.setLineSpacing(0, 1.18f);
        publicServicesCard.addView(discoveredServicesView);
        serviceRoot.addView(publicServicesCard, sectionParams());
        serviceSpinner.setOnItemSelectedListener(new SimpleItemSelectedListener(position -> {
            if (!updatingCharacteristicSpinners) {
                if (communicationServiceOpen) closeCommunicationService();
                updateCharacteristicOptions();
            }
        }));
        notifySpinner.setOnItemSelectedListener(new SimpleItemSelectedListener(position -> {
            if (!updatingCharacteristicSpinners && communicationServiceOpen) {
                if (notificationCharacteristic != null) {
                    CharacteristicEntry previous = findCharacteristic(notificationCharacteristic);
                    if (previous != null) enableNotifications(previous, false);
                }
                enableNotifications(getSelected(notifyOptions, notifySpinner), true);
            }
        }));
        communicationServiceSwitch.setOnCheckedChangeListener((buttonView, isChecked) -> {
            if (updatingCommunicationSwitch) return;
            if (isChecked) {
                if (!openCommunicationService()) syncCommunicationSwitch(false);
            } else {
                closeCommunicationService();
            }
        });
        serviceActionRow.setOnClickListener(v -> {
            if (communicationServiceSwitch.isEnabled()) {
                communicationServiceSwitch.setChecked(!communicationServiceSwitch.isChecked());
            } else {
                toast(connected ? "正在读取 GATT 服务，请稍候" : "请先连接 BLE 设备");
            }
        });
        txChannelSwitch.setOnCheckedChangeListener((buttonView, isChecked) -> {
            if (updatingChannelSwitches) return;
            if (isChecked) {
                if (!openTxChannel()) syncTxSwitch(false);
            } else {
                closeTxChannel();
            }
        });
        txActionRow.setOnClickListener(v -> {
            if (txChannelSwitch.isEnabled()) txChannelSwitch.setChecked(!txChannelSwitch.isChecked());
            else toast(communicationServiceOpen ? "未发现 TX 通道" : "请先打开配置服务");
        });
        rxChannelSwitch.setOnCheckedChangeListener((buttonView, isChecked) -> {
            if (updatingChannelSwitches) return;
            if (isChecked) {
                if (!openRxChannel()) syncRxSwitch(false);
            } else {
                closeRxChannel();
            }
        });
        rxActionRow.setOnClickListener(v -> {
            if (rxChannelSwitch.isEnabled()) rxChannelSwitch.setChecked(!rxChannelSwitch.isChecked());
            else toast(communicationServiceOpen ? "未发现 RX 通道" : "请先打开配置服务");
        });
        readButton.setOnClickListener(v -> readSelectedCharacteristic());

        LinearLayout sendCard = section("发送 AT 命令");
        atRoot.addView(sendCard, sectionParams());
        atChannelStatusView = text("服务：关闭  ·  TX：关闭  ·  RX：关闭", 13, 0xFFC62828, true);
        LinearLayout.LayoutParams atChannelParams = new LinearLayout.LayoutParams(-1, -2);
        atChannelParams.bottomMargin = dp(10);
        sendCard.addView(atChannelStatusView, atChannelParams);
        LinearLayout activationRow = horizontal();
        activationStatusRow = activationRow;
        activationRow.addView(text("激活状态", 14, COLOR_TEXT, true), new LinearLayout.LayoutParams(0, -2, 1));
        activationStatusView = text("未知", 14, 0xFF687386, true);
        activationStatusView.setGravity(Gravity.CENTER);
        activationStatusView.setPadding(dp(14), dp(7), dp(14), dp(7));
        setActivationState(null);
        activationRow.addView(activationStatusView, new LinearLayout.LayoutParams(-2, dp(36)));
        LinearLayout.LayoutParams activationRowParams = new LinearLayout.LayoutParams(-1, -2);
        activationRowParams.bottomMargin = dp(10);
        sendCard.addView(activationRow, activationRowParams);
        activationStatusRow.setVisibility(View.GONE);
        commandInput = new EditText(this);
        commandInput.setSingleLine(true);
        commandInput.setTextColor(COLOR_TEXT);
        commandInput.setHintTextColor(0xFF8793A5);
        commandInput.setHint("请输入 AT 命令");
        commandInput.setTextSize(15);
        commandInput.setInputType(InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_FLAG_NO_SUGGESTIONS);
        commandInput.setPadding(dp(13), dp(10), dp(13), dp(10));
        commandInput.setBackground(fieldBackground());
        sendCard.addView(commandInput, fieldParams());
        commandPresetSpinner = spinner();
        setSpinnerItems(commandPresetSpinner, new String[]{
                "选择预设 AT 命令（可选）",
                "AT+ACTIVATION_CONTROL?",
                "AT+ACTIVATION_CONTROL=0",
                "AT+ACTIVATION_CONTROL=1",
                "AT+ACTIVATION_CONTROL=2"
        }, 0);
        commandPresetSpinner.setOnItemSelectedListener(new SimpleItemSelectedListener(position -> {
            if (position <= 0) return;
            Object selected = commandPresetSpinner.getSelectedItem();
            if (selected == null) return;
            commandInput.setText(selected.toString());
            commandInput.setSelection(commandInput.length());
        }));
        LinearLayout.LayoutParams presetParams = new LinearLayout.LayoutParams(-1, dp(48));
        presetParams.bottomMargin = dp(10);
        sendCard.addView(commandPresetSpinner, presetParams);
        LinearLayout sendRow = horizontal();
        suffixSpinner = spinner();
        setSpinnerItems(suffixSpinner, new String[]{"结尾：\\r\\n", "结尾：\\n", "不追加"}, 0);
        sendButton = button("发送", 0xFF087F72);
        sendButton.setEnabled(false);
        sendRow.addView(suffixSpinner, weightParams(1.35f, 0, dp(8)));
        sendRow.addView(sendButton, weightParams(1, 0, 0));
        LinearLayout.LayoutParams sendRowParams = new LinearLayout.LayoutParams(-1, -2);
        sendRowParams.topMargin = dp(10);
        sendCard.addView(sendRow, sendRowParams);
        sendButton.setOnClickListener(v -> sendCommand());

        LinearLayout terminalCard = section("AT 日志（含时间戳）");
        atRoot.addView(terminalCard, sectionParams());
        LinearLayout terminalHeader = horizontal();
        terminalHeader.setGravity(Gravity.CENTER_VERTICAL);
        TextView terminalHint = text("UTF-8 文本 · 实时接收", 12, COLOR_TEXT_SECONDARY, false);
        Button clearButton = button("清空", 0xFF29354A);
        terminalHeader.addView(terminalHint, new LinearLayout.LayoutParams(0, -2, 1));
        terminalHeader.addView(clearButton, new LinearLayout.LayoutParams(-2, dp(36)));
        terminalCard.addView(terminalHeader);
        logScroll = new ScrollView(this);
        logScroll.setFillViewport(false);
        logView = text("等待连接 BLE 设备…", 13, COLOR_TEXT, false);
        logView.setTypeface(Typeface.MONOSPACE);
        logView.setTextIsSelectable(true);
        logView.setPadding(dp(12), dp(10), dp(12), dp(10));
        logScroll.setBackground(fieldBackground());
        logScroll.addView(logView);
        LinearLayout.LayoutParams logParams = new LinearLayout.LayoutParams(-1, dp(220));
        logParams.topMargin = dp(10);
        terminalCard.addView(logScroll, logParams);
        clearButton.setOnClickListener(v -> logView.setText(""));

        scanButton.setOnClickListener(v -> beginScan());
        connectButton.setOnClickListener(v -> toggleConnection());
        pairButton.setOnClickListener(v -> togglePairing());
        screenContainer = new FrameLayout(this);
        screenContainer.addView(mainPage, new FrameLayout.LayoutParams(-1, -1));
        workspacePage.setVisibility(View.GONE);
        screenContainer.addView(workspacePage, new FrameLayout.LayoutParams(-1, -1));
        setContentView(screenContainer);
    }

    private void showMainScreen() {
        if (mainPage == null || workspacePage == null) return;
        mainPage.setVisibility(View.VISIBLE);
        workspacePage.setVisibility(View.GONE);
    }

    private void showWorkspaceScreen() {
        if (mainPage == null || workspacePage == null) return;
        mainPage.setVisibility(View.GONE);
        workspacePage.setVisibility(View.VISIBLE);
        showServiceTab();
        updateConnectedHeader();
    }

    private void showServiceTab() {
        if (servicePage == null || atPage == null) return;
        servicePage.setVisibility(View.VISIBLE);
        atPage.setVisibility(View.GONE);
        styleTabButton(serviceTabButton, true);
        styleTabButton(atTabButton, false);
    }

    private void showAtTab() {
        if (servicePage == null || atPage == null) return;
        servicePage.setVisibility(View.GONE);
        atPage.setVisibility(View.VISIBLE);
        styleTabButton(serviceTabButton, false);
        styleTabButton(atTabButton, true);
    }

    private void styleTabButton(Button button, boolean selected) {
        if (button == null) return;
        button.setTextColor(selected ? Color.WHITE : COLOR_TEXT);
        button.setBackground(rounded(selected ? COLOR_TEAL : 0xFFE2E9F0, dp(10)));
    }

    private void updateConnectedHeader() {
        if (connectedDeviceHeader == null || connectedStatusHeader == null) return;
        if (selectedDevice == null) {
            connectedDeviceHeader.setText("尚未选择 BLE 设备");
        } else {
            connectedDeviceHeader.setText(safeName(selectedDevice) + "  ·  " + safeAddress(selectedDevice));
        }
        if (connected) {
            connectedStatusHeader.setText("● BLE 已连接"
                    + (communicationServiceOpen ? "  ·  服务开" : "")
                    + (txChannelOpen ? "  ·  TX开" : "")
                    + (rxChannelOpen ? "  ·  RX开" : ""));
            connectedStatusHeader.setTextColor(0xFF087443);
        } else {
            connectedStatusHeader.setText("● BLE 已断开");
            connectedStatusHeader.setTextColor(0xFFC62828);
        }
    }

    @Override
    public void onBackPressed() {
        if (workspacePage != null && workspacePage.getVisibility() == View.VISIBLE) {
            showMainScreen();
            return;
        }
        super.onBackPressed();
    }

    private void beginScan() {
        if (!hasBlePermissions()) {
            requestPermissions(requiredPermissions(), REQUEST_BLE_PERMISSIONS);
            return;
        }
        // MIUI 13 的部分机型即使运行 Android 12，也会在位置信息关闭时
        // 静默返回 0 个 BLE 结果，因此所有系统版本都在扫描时检查一次。
        if (!isLocationServiceEnabled()) {
            showLocationRequiredDialog();
            return;
        }
        if (!bluetoothAdapter.isEnabled()) {
            toast("请先在系统设置中打开蓝牙");
            return;
        }
        scanner = bluetoothAdapter.getBluetoothLeScanner();
        if (scanner == null) {
            toast("无法启动 BLE 扫描，请检查蓝牙状态");
            return;
        }
        stopScan("重新扫描");
        devices.clear();
        deviceNames.clear();
        deviceAddresses.clear();
        deviceRows.clear();
        deviceIndexByAddress.clear();
        renderDevices();
        selectedDevice = null;
        selectedDeviceView.setText("当前选择：无");
        updatePairButton();
        setActivationState(null);
        pendingActivationCommand = "";
        activationResponseBuffer.setLength(0);
        connectButton.setEnabled(false);
        scanning = true;
        scanButton.setText("扫描中…");
        setStatus("正在扫描附近 BLE 设备…");
        try {
            ScanSettings settings = new ScanSettings.Builder()
                    .setScanMode(ScanSettings.SCAN_MODE_LOW_LATENCY)
                    .setReportDelay(0)
                    .build();
            scanner.startScan(null, settings, scanCallback);
            handler.postDelayed(stopScanRunnable, SCAN_DURATION_MS);
        } catch (SecurityException e) {
            scanning = false;
            scanButton.setText("扫描 BLE");
            setStatus("蓝牙扫描权限未授予");
        }
    }

    private final ScanCallback scanCallback = new ScanCallback() {
        @Override
        public void onScanResult(int callbackType, ScanResult result) {
            runOnUiThread(() -> acceptScanResult(result));
        }

        @Override
        public void onScanFailed(int errorCode) {
            runOnUiThread(() -> {
                scanning = false;
                scanButton.setText("扫描 BLE");
                setStatus("扫描失败，错误码 " + errorCode);
            });
        }
    };

    private void acceptScanResult(ScanResult result) {
        BluetoothDevice device = result.getDevice();
        if (device == null) return;
        String address;
        String name;
        try {
            address = device.getAddress();
            name = device.getName();
        } catch (SecurityException e) {
            return;
        }
        if ((name == null || name.trim().isEmpty()) && result.getScanRecord() != null) {
            name = result.getScanRecord().getDeviceName();
        }
        String displayName = name == null || name.trim().isEmpty() ? "未命名 BLE 设备" : name.trim();
        String addressKey = address.toLowerCase(Locale.ROOT);
        Integer knownIndex = deviceIndexByAddress.get(addressKey);
        int existingIndex = knownIndex == null ? -1 : knownIndex;
        if (existingIndex >= 0) {
            boolean learnedName = "未命名 BLE 设备".equals(deviceNames.get(existingIndex))
                    && !"未命名 BLE 设备".equals(displayName);
            if (!learnedName) return;
            deviceNames.set(existingIndex, displayName);
            deviceRows.set(existingIndex, displayName + "\n" + address + "  ·  RSSI " + result.getRssi() + " dBm");
        } else {
            int newIndex = devices.size();
            devices.add(device);
            deviceNames.add(displayName);
            deviceAddresses.add(address);
            deviceRows.add(displayName + "\n" + address + "  ·  RSSI " + result.getRssi() + " dBm");
            deviceIndexByAddress.put(addressKey, newIndex);
        }
        scheduleDeviceListRefresh(DEVICE_LIST_REFRESH_INTERVAL_MS, false);
    }

    private void renderDevices() {
        if (deviceListAdapter == null) return;
        filteredDeviceIndices.clear();
        for (int i = 0; i < devices.size(); i++) {
            if (!deviceMatchesFilters(i)) continue;
            filteredDeviceIndices.add(i);
        }
        deviceListAdapter.notifyDataSetChanged();
        updateDeviceListHeight(filteredDeviceIndices.size());
    }

    private void updateDeviceListHeight(int visibleCount) {
        if (deviceListView == null) return;
        int rows = visibleCount <= 0 ? 1 : Math.min(visibleCount, 10);
        int desiredHeight = visibleCount <= 0 ? dp(54) : dp(rows * 54 + 6);
        ViewGroup.LayoutParams params = deviceListView.getLayoutParams();
        boolean needsLayoutParams = params == null;
        if (needsLayoutParams) params = new LinearLayout.LayoutParams(-1, desiredHeight);
        if (needsLayoutParams || params.height != desiredHeight) {
            params.height = desiredHeight;
            deviceListView.setLayoutParams(params);
        }
    }

    private void handleDeviceTap(int index) {
        if (index < 0 || index >= devices.size()) return;
        BluetoothDevice device = devices.get(index);
        stopScan("已选择设备");
        boolean sameSelection = selectedDevice != null && sameDevice(selectedDevice, device);
        selectedDevice = device;
        updateSelectedDeviceLabel();
        updatePairButton();
        renderDevices();

        if (sameSelection && (connected || connecting)
                && bluetoothGatt != null && sameDevice(bluetoothGatt.getDevice(), device)) {
            setStatus(connected ? "设备已连接" : "设备正在连接…");
            return;
        }
        setActivationState(null);
        pendingActivationCommand = "";
        activationResponseBuffer.setLength(0);

        if (bluetoothGatt != null) {
            pendingAutoConnectDevice = device;
            setStatus("正在切换 BLE 设备…");
            disconnectGatt();
        } else {
            connectSelectedDevice();
        }
    }

    private void togglePairing() {
        if (selectedDevice == null) {
            toast("请先选择 BLE 设备");
            return;
        }
        int state = safeBondState(selectedDevice);
        if (state == BluetoothDevice.BOND_BONDED || state == BluetoothDevice.BOND_BONDING) {
            requestUnpair(selectedDevice);
            return;
        }
        try {
            boolean started = selectedDevice.createBond();
            if (started) {
                setStatus("正在配对 " + safeAddress(selectedDevice) + "…");
                appendLog("[配对] 用户主动发起系统配对：" + safeAddress(selectedDevice) + "\n");
                updatePairButton();
            } else {
                toast("设备不支持配对，或系统拒绝启动配对");
            }
        } catch (SecurityException e) {
            toast("缺少附近设备权限");
        }
    }

    private void updatePairButton() {
        if (pairButton == null) return;
        pairButton.setEnabled(selectedDevice != null);
        if (selectedDevice == null) {
            pairButton.setText("配对");
            return;
        }
        int state = safeBondState(selectedDevice);
        if (state == BluetoothDevice.BOND_BONDED) pairButton.setText("取消配对");
        else if (state == BluetoothDevice.BOND_BONDING) pairButton.setText("取消配对");
        else pairButton.setText("配对");
    }

    private void requestUnpair(BluetoothDevice device) {
        int state = safeBondState(device);
        if (state == BluetoothDevice.BOND_NONE) {
            setStatus("设备当前未配对");
            return;
        }
        String methodName = state == BluetoothDevice.BOND_BONDING ? "cancelBondProcess" : "removeBond";
        boolean requested = invokeBondMethod(device, methodName);
        if (requested) {
            setStatus("正在取消配对…");
            appendLog("[配对] 已请求取消配对：" + safeAddress(device) + "\n");
        } else {
            setStatus("系统限制应用直接取消配对");
            showManualUnpairDialog();
        }
    }

    private boolean invokeBondMethod(BluetoothDevice device, String methodName) {
        try {
            java.lang.reflect.Method method = device.getClass().getMethod(methodName);
            method.setAccessible(true);
            Object result = method.invoke(device);
            return result instanceof Boolean && (Boolean) result;
        } catch (Exception ignored) {
            return false;
        }
    }

    private void showManualUnpairDialog() {
        new AlertDialog.Builder(this)
                .setTitle("请在系统中取消配对")
                .setMessage("当前 MIUI 阻止第三方应用直接删除系统配对记录。请在蓝牙设置中点击该设备并选择“取消配对”。")
                .setNegativeButton("稍后", null)
                .setPositiveButton("打开蓝牙设置", (dialog, which) -> {
                    try {
                        startActivity(new Intent(Settings.ACTION_BLUETOOTH_SETTINGS));
                    } catch (Exception e) {
                        toast("请手动打开系统蓝牙设置");
                    }
                })
                .show();
    }

    private void updateSelectedDeviceLabel() {
        if (selectedDevice == null) {
            selectedDeviceView.setText("当前选择：无");
            return;
        }
        String address = safeAddress(selectedDevice);
        for (int i = 0; i < deviceAddresses.size(); i++) {
            if (deviceAddresses.get(i).equalsIgnoreCase(address)) {
                selectedDeviceView.setText("当前选择：" + deviceNames.get(i) + "  " + address
                        + "  ·  " + bondStateLabel(selectedDevice)
                        + (isGattConnectedDevice(selectedDevice) ? "  ·  已连接" : "")
                        + "（点击设备直接连接）");
                return;
            }
        }
        selectedDeviceView.setText("当前选择：" + address + "  ·  " + bondStateLabel(selectedDevice)
                + (isGattConnectedDevice(selectedDevice) ? "  ·  已连接" : ""));
    }

    private String bondStateLabel(BluetoothDevice device) {
        int state = safeBondState(device);
        if (state == BluetoothDevice.BOND_BONDED) return "已配对";
        if (state == BluetoothDevice.BOND_BONDING) return "配对中";
        return "未配对（BLE 可直连）";
    }

    private int safeBondState(BluetoothDevice device) {
        try {
            return device.getBondState();
        } catch (SecurityException ignored) {
            return BluetoothDevice.BOND_NONE;
        }
    }

    private boolean sameDevice(BluetoothDevice first, BluetoothDevice second) {
        return safeAddress(first).equalsIgnoreCase(safeAddress(second));
    }

    private boolean isGattConnectedDevice(BluetoothDevice device) {
        return connected && bluetoothGatt != null && sameDevice(bluetoothGatt.getDevice(), device);
    }

    private void onDeviceFilterChanged() {
        if (deviceListAdapter == null) return;
        scheduleDeviceListRefresh(100, true);
    }

    private void scheduleDeviceListRefresh(long delayMs, boolean restartTimer) {
        if (restartTimer && deviceListRefreshScheduled) {
            handler.removeCallbacks(deviceListRefreshRunnable);
            deviceListRefreshScheduled = false;
        }
        if (deviceListRefreshScheduled) return;
        deviceListRefreshScheduled = true;
        handler.postDelayed(deviceListRefreshRunnable, Math.max(0, delayMs));
    }

    private boolean deviceMatchesFilters(int index) {
        if (index < 0 || index >= deviceNames.size() || index >= deviceAddresses.size()) return false;
        String nameFilter = nameFilterInput == null ? "" : nameFilterInput.getText().toString().trim().toLowerCase(Locale.ROOT);
        String macFilter = macFilterInput == null ? "" : normalizeMac(macFilterInput.getText().toString());
        String deviceName = deviceNames.get(index).toLowerCase(Locale.ROOT);
        String deviceMac = normalizeMac(deviceAddresses.get(index));
        return (nameFilter.isEmpty() || deviceName.contains(nameFilter))
                && (macFilter.isEmpty() || deviceMac.contains(macFilter));
    }

    private int visibleDeviceCount() {
        int count = 0;
        for (int i = 0; i < devices.size(); i++) if (deviceMatchesFilters(i)) count++;
        return count;
    }

    private String scanProgressText() {
        int visible = visibleDeviceCount();
        if (visible == devices.size()) return "扫描中 · 已发现 " + devices.size() + " 台设备";
        return "扫描中 · 已发现 " + devices.size() + " 台，过滤后显示 " + visible + " 台";
    }

    private String normalizeMac(String value) {
        return value == null ? "" : value.replace(":", "")
                .replace("-", "")
                .replace(" ", "")
                .trim()
                .toLowerCase(Locale.ROOT);
    }

    private void toggleConnection() {
        if (connected || connecting || bluetoothGatt != null) {
            pendingAutoConnectDevice = null;
            connectButton.setText("断开中…");
            connectButton.setEnabled(false);
            disconnectGatt();
            return;
        }
        connectSelectedDevice();
    }

    private void connectSelectedDevice() {
        if (selectedDevice == null) {
            toast("请先点选一台 BLE 设备");
            return;
        }
        if (!hasBlePermissions()) {
            requestPermissions(requiredPermissions(), REQUEST_BLE_PERMISSIONS);
            return;
        }
        services.clear();
        writeOptions.clear();
        notifyOptions.clear();
        negotiatedMtu = 23;
        abortWriteSequence(null);
        setCommunicationServiceOpen(false);
        communicationServiceSwitch.setEnabled(false);
        syncCommunicationSwitch(false);
        readButton.setEnabled(false);
        sendButton.setEnabled(false);
        setStatus("正在连接 " + safeName(selectedDevice) + "…");
        try {
            connecting = true;
            bluetoothGatt = selectedDevice.connectGatt(this, false, gattCallback, BluetoothDevice.TRANSPORT_LE);
            connectButton.setText("连接中…");
            connectButton.setEnabled(true);
        } catch (SecurityException e) {
            connecting = false;
            setStatus("蓝牙连接权限未授予");
        }
    }

    private final BluetoothGattCallback gattCallback = new BluetoothGattCallback() {
        @Override
        public void onConnectionStateChange(BluetoothGatt gatt, int status, int newState) {
            runOnUiThread(() -> {
                if (status != BluetoothGatt.GATT_SUCCESS) {
                    appendLog("[连接错误] GATT status=" + status + "\n");
                    connected = false;
                    connecting = false;
                    resetConnectionUi("连接异常 · GATT " + status);
                    closeGatt(gatt);
                    return;
                }
                if (newState == BluetoothProfile.STATE_CONNECTED) {
                    connected = true;
                    connecting = false;
                    connectButton.setText("已连接");
                    connectButton.setEnabled(true);
                    sendButton.setEnabled(false);
                    setCommunicationServiceOpen(false);
                    setStatus("已连接 · 正在读取 BLE 服务…");
                    appendLog("[系统] BLE 已连接：" + safeName(gatt.getDevice()) + "\n");
                    renderDevices();
                    updateSelectedDeviceLabel();
                    showWorkspaceScreen();
                    updateConnectedHeader();
                    try {
                        // GATT 同一时刻只能可靠执行一个异步操作。MIUI 上先请求 MTU 再立即
                        // discoverServices 可能被判定为忙碌，因此先完成最重要的服务发现。
                        boolean started = gatt.discoverServices();
                        if (started) {
                            appendLog("[系统] 正在发现 GATT 服务…\n");
                            setStatus("已连接 · 正在发现 GATT 服务…");
                        } else {
                            appendLog("[错误] 系统未能启动 GATT 服务发现，将在点击服务开关时重试。\n");
                            setStatus("已连接 · 服务发现启动失败");
                        }
                    } catch (SecurityException e) {
                        appendLog("[错误] 缺少蓝牙连接权限\n");
                    }
                } else if (newState == BluetoothProfile.STATE_DISCONNECTED) {
                    connected = false;
                    connecting = false;
                    BluetoothDevice nextDevice = pendingAutoConnectDevice;
                    pendingAutoConnectDevice = null;
                    resetConnectionUi("已断开连接");
                    appendLog("[系统] BLE 连接已断开\n");
                    closeGatt(gatt);
                    renderDevices();
                    updateSelectedDeviceLabel();
                    updateConnectedHeader();
                    if (nextDevice != null) {
                        selectedDevice = nextDevice;
                        updateSelectedDeviceLabel();
                        updatePairButton();
                        handler.postDelayed(MainActivity.this::connectSelectedDevice, 250);
                    }
                }
            });
        }

        @Override
        public void onServicesDiscovered(BluetoothGatt gatt, int status) {
            runOnUiThread(() -> {
                if (status != BluetoothGatt.GATT_SUCCESS) {
                    appendLog("[错误] 读取 BLE 服务失败：" + status + "\n");
                    setStatus("服务读取失败 · GATT " + status);
                    return;
                }
                services.clear();
                for (BluetoothGattService service : gatt.getServices()) {
                    ServiceEntry entry = new ServiceEntry(service);
                    for (BluetoothGattCharacteristic characteristic : service.getCharacteristics()) {
                        CharacteristicEntry characteristicEntry = new CharacteristicEntry(service.getUuid(), characteristic);
                        entry.characteristics.add(characteristicEntry);
                        appendLog("[GATT] " + service.getUuid() + " / " + characteristic.getUuid()
                                + "  " + propertyLabel(characteristic.getProperties()) + "\n");
                    }
                    services.add(entry);
                }
                if (services.isEmpty()) {
                    setStatus("已连接，但设备没有公布 GATT 服务");
                    appendLog("[提示] 未发现 GATT 服务\n");
                    return;
                }
                List<String> labels = new ArrayList<>();
                for (ServiceEntry service : services) {
                    labels.add(serviceDisplayName(service.service.getUuid()) + "  ·  " + shortUuid(service.service.getUuid())
                            + (hasWritableCharacteristic(service) ? "  [可写]" : "")
                            + "  ·  " + service.characteristics.size() + " 个特征值");
                }
                int automaticService = bestServiceIndex();
                setCommunicationServiceOpen(false);
                updatingCharacteristicSpinners = true;
                setSpinnerItems(serviceSpinner, labels.toArray(new String[0]), automaticService);
                updatingCharacteristicSpinners = false;
                updateCharacteristicOptions();
                updateDiscoveredServicesPanel();
                appendLog("[系统] 已发现 " + services.size() + " 个 BLE 服务\n");
                boolean isPrivateConfigService = CONFIG_SERVICE_UUID.equalsIgnoreCase(
                        services.get(automaticService).service.getUuid().toString());
                if (isPrivateConfigService) {
                    appendLog("[系统] 已找到配置通信服务 UUID " + CONFIG_SERVICE_UUID + "\n");
                    setStatus("已连接 · 已选择 BLE 配置通信服务，请打开服务");
                } else if (hasWritableCharacteristic(services.get(automaticService))) {
                    setStatus("已连接 · 已自动选择可写服务 " + shortUuid(services.get(automaticService).service.getUuid()));
                    appendLog("[系统] 自动选择可写服务 " + services.get(automaticService).service.getUuid() + "\n");
                } else {
                    setStatus("已连接，但所有服务均未发现可写特征值");
                    appendLog("[提示] 所有 GATT 服务均无 WRITE / WRITE_NO_RESPONSE 特征值，请确认设备支持 BLE UART/AT 透传。\n");
                }
                try {
                    if (Build.VERSION.SDK_INT >= 21 && gatt.requestMtu(247)) {
                        appendLog("[MTU] 服务发现完成，正在请求 MTU 247…\n");
                    } else {
                        appendLog("[MTU] 设备未接受 MTU 请求，将按默认 20 字节自动分包。\n");
                    }
                } catch (SecurityException e) {
                    appendLog("[MTU] 无法请求 MTU，将按默认 20 字节自动分包。\n");
                }
            });
        }

        @Override
        public void onMtuChanged(BluetoothGatt gatt, int mtu, int status) {
            runOnUiThread(() -> {
                negotiatedMtu = status == BluetoothGatt.GATT_SUCCESS ? Math.max(23, mtu) : 23;
                appendLog("[MTU] " + (status == BluetoothGatt.GATT_SUCCESS ? "协商成功" : "协商失败")
                        + "，MTU=" + negotiatedMtu + "，单包有效载荷=" + Math.max(20, negotiatedMtu - 3) + " 字节\n");
            });
        }

        @Override
        public void onCharacteristicChanged(BluetoothGatt gatt, BluetoothGattCharacteristic characteristic) {
            byte[] value = characteristic.getValue();
            if (value != null) receiveBytes(value);
        }

        @Override
        public void onCharacteristicChanged(BluetoothGatt gatt, BluetoothGattCharacteristic characteristic, byte[] value) {
            receiveBytes(value);
        }

        @Override
        public void onCharacteristicWrite(BluetoothGatt gatt, BluetoothGattCharacteristic characteristic, int status) {
            runOnUiThread(() -> {
                if (status == BluetoothGatt.GATT_SUCCESS) {
                    handleWriteChunkSuccess(characteristic);
                } else {
                    appendLog("[发送失败] " + characteristic.getUuid() + " · GATT status=" + status + "\n");
                    if (writeSequenceActive && !writeFallbackAttempted && pendingWritePayload.length > 0) {
                        if (tryAlternatePrivateWrite(characteristic, pendingWritePayload)) {
                            activeWriteCharacteristic = pendingWriteCharacteristic;
                            appendLog("[TX] 已自动切换另一条私有特征值重试\n");
                            return;
                        }
                    }
                    abortWriteSequence("写入失败，GATT status=" + status);
                }
            });
        }

        @Override
        public void onDescriptorWrite(BluetoothGatt gatt, BluetoothGattDescriptor descriptor, int status) {
            if (!CCCD_UUID.equals(descriptor.getUuid())) return;
            runOnUiThread(() -> {
                notificationChangePending = false;
                if (status == BluetoothGatt.GATT_SUCCESS) {
                    notificationsEnabled = requestedNotificationsEnabled;
                    appendLog("[服务] RX Notify/Indicate " + (notificationsEnabled ? "已开启" : "已关闭") + "\n");
                } else {
                    notificationsEnabled = false;
                    appendLog("[服务错误] 设置 RX Notify/Indicate 失败，GATT status=" + status + "\n");
                    CharacteristicEntry rx = getSelected(notifyOptions, notifySpinner);
                    if (rxChannelOpen && rx != null
                            && (rx.characteristic.getProperties() & BluetoothGattCharacteristic.PROPERTY_READ) == 0) {
                        rxChannelOpen = false;
                        syncRxSwitch(false);
                        setStatus("RX 打开失败 · 无法启用接收通知");
                    }
                }
                updateCommunicationControls();
            });
        }

        @Override
        public void onCharacteristicRead(BluetoothGatt gatt, BluetoothGattCharacteristic characteristic, int status) {
            byte[] value = characteristic.getValue();
            runOnUiThread(() -> {
                if (status == BluetoothGatt.GATT_SUCCESS && value != null) {
                    String received = new String(value, StandardCharsets.UTF_8);
                    appendLog("[RX-READ] " + received + "\n");
                    analyzeActivationResponse(received);
                } else {
                    appendLog("[读取失败] GATT status=" + status + "\n");
                }
                updateCommunicationControls();
            });
        }

        @Override
        public void onCharacteristicRead(BluetoothGatt gatt, BluetoothGattCharacteristic characteristic,
                                         byte[] value, int status) {
            byte[] result = value == null ? new byte[0] : value.clone();
            runOnUiThread(() -> {
                if (status == BluetoothGatt.GATT_SUCCESS) {
                    String received = new String(result, StandardCharsets.UTF_8);
                    appendLog("[RX-READ] " + received + "\n");
                    analyzeActivationResponse(received);
                } else {
                    appendLog("[读取失败] GATT status=" + status + "\n");
                }
                updateCommunicationControls();
            });
        }
    };

    private void updateDiscoveredServicesPanel() {
        if (discoveredServicesView == null) return;
        StringBuilder text = new StringBuilder();
        text.append("GAP/GATT 是基础标准服务；设备信息、电池等公开服务属于可选实现。\n\n常见公开服务：\n");
        String[][] common = {
                {"1800", "Generic Access（通用访问）"},
                {"1801", "Generic Attribute（通用属性）"},
                {"180a", "Device Information（设备信息）"},
                {"180f", "Battery Service（电池）"},
                {"1805", "Current Time（当前时间）"},
                {"181a", "Environmental Sensing（环境感知）"}
        };
        for (String[] item : common) {
            text.append(hasDiscoveredService(item[0]) ? "✓ " : "— ")
                    .append(item[1]).append("  0x").append(item[0].toUpperCase(Locale.ROOT)).append('\n');
        }
        text.append("\n本设备实际发现的服务：\n");
        for (ServiceEntry service : services) {
            UUID serviceUuid = service.service.getUuid();
            text.append("\n• ").append(serviceDisplayName(serviceUuid)).append("\n  ")
                    .append(serviceUuid).append('\n');
            for (CharacteristicEntry entry : service.characteristics) {
                text.append("    - ").append(characteristicDisplayName(entry.characteristic.getUuid()))
                        .append("\n      ").append(entry.characteristic.getUuid())
                        .append("  [").append(propertyLabel(entry.characteristic.getProperties())).append("]\n");
            }
        }
        discoveredServicesView.setText(text.toString().trim());
    }

    private boolean hasDiscoveredService(String shortId) {
        for (ServiceEntry service : services) {
            if (shortUuid(service.service.getUuid()).equalsIgnoreCase(shortId)) return true;
        }
        return false;
    }

    private String serviceDisplayName(UUID uuid) {
        String value = uuid.toString().toLowerCase(Locale.ROOT);
        if (value.equals(CONFIG_SERVICE_UUID)) return "私有 BLE 配置通信服务";
        String id = shortUuid(uuid).toLowerCase(Locale.ROOT);
        switch (id) {
            case "1800": return "Generic Access（通用访问）";
            case "1801": return "Generic Attribute（通用属性）";
            case "1805": return "Current Time（当前时间）";
            case "180a": return "Device Information（设备信息）";
            case "180d": return "Heart Rate（心率）";
            case "180f": return "Battery Service（电池）";
            case "1812": return "Human Interface Device（HID）";
            case "1816": return "Cycling Speed and Cadence（骑行）";
            case "181a": return "Environmental Sensing（环境感知）";
            case "181c": return "User Data（用户数据）";
            case "1826": return "Fitness Machine（健身设备）";
            default: return "自定义服务";
        }
    }

    private String characteristicDisplayName(UUID uuid) {
        String value = uuid.toString().toLowerCase(Locale.ROOT);
        if (value.equals(CONFIG_TX_UUID)) return "TX_CHR（设备发送 / App 接收）";
        if (value.equals(CONFIG_RX_UUID)) return "RX_CHR（设备接收 / App 写入）";
        switch (shortUuid(uuid).toLowerCase(Locale.ROOT)) {
            case "2a00": return "Device Name（设备名称）";
            case "2a01": return "Appearance（外观）";
            case "2a04": return "Peripheral Preferred Connection Parameters（连接参数）";
            case "2a05": return "Service Changed（服务变更）";
            case "2a19": return "Battery Level（电量）";
            case "2a23": return "System ID（系统标识）";
            case "2a24": return "Model Number（型号）";
            case "2a25": return "Serial Number（序列号）";
            case "2a26": return "Firmware Revision（固件版本）";
            case "2a27": return "Hardware Revision（硬件版本）";
            case "2a28": return "Software Revision（软件版本）";
            case "2a29": return "Manufacturer Name（制造商）";
            default: return "特征值";
        }
    }

    private int bestServiceIndex() {
        int bestIndex = 0;
        int bestScore = Integer.MIN_VALUE;
        for (int i = 0; i < services.size(); i++) {
            ServiceEntry service = services.get(i);
            int score = 0;
            boolean hasWrite = false;
            boolean hasNotify = false;
            String serviceUuid = service.service.getUuid().toString().toLowerCase(Locale.ROOT);
            if (serviceUuid.equals(CONFIG_SERVICE_UUID)) score += 10_000;
            if (serviceUuid.contains("0000ffe0")) score += 40;
            if (serviceUuid.contains("6e400001")) score += 60;
            for (CharacteristicEntry entry : service.characteristics) {
                int properties = entry.characteristic.getProperties();
                boolean writable = (properties & (BluetoothGattCharacteristic.PROPERTY_WRITE
                        | BluetoothGattCharacteristic.PROPERTY_WRITE_NO_RESPONSE)) != 0;
                boolean notifiable = (properties & (BluetoothGattCharacteristic.PROPERTY_NOTIFY
                        | BluetoothGattCharacteristic.PROPERTY_INDICATE)) != 0;
                String uuid = entry.characteristic.getUuid().toString().toLowerCase(Locale.ROOT);
                if (writable) {
                    hasWrite = true;
                    score += 30;
                    if (uuid.equals(CONFIG_RX_UUID)) score += 2_000;
                    if (uuid.equals(CONFIG_TX_UUID)) score += 500;
                    if (uuid.contains(NORDIC_WRITE_UUID)) score += 160;
                    if (uuid.contains(UART_TX_UUID)) score += 140;
                }
                if (notifiable) {
                    hasNotify = true;
                    score += 15;
                    if (uuid.equals(CONFIG_TX_UUID)) score += 2_000;
                    if (uuid.equals(CONFIG_RX_UUID)) score += 500;
                    if (uuid.contains(NORDIC_NOTIFY_UUID)) score += 120;
                    if (uuid.contains(UART_TX_UUID)) score += 100;
                }
            }
            if (hasWrite && hasNotify) score += 50;
            if (!hasWrite) score -= 1000;
            if (score > bestScore) {
                bestScore = score;
                bestIndex = i;
            }
        }
        return bestIndex;
    }

    private boolean hasWritableCharacteristic(ServiceEntry service) {
        if (service == null) return false;
        for (CharacteristicEntry entry : service.characteristics) {
            int properties = entry.characteristic.getProperties();
            if ((properties & (BluetoothGattCharacteristic.PROPERTY_WRITE
                    | BluetoothGattCharacteristic.PROPERTY_WRITE_NO_RESPONSE)) != 0) return true;
        }
        return false;
    }

    private void updateCharacteristicOptions() {
        writeOptions.clear();
        notifyOptions.clear();
        int serviceIndex = serviceSpinner.getSelectedItemPosition();
        if (serviceIndex < 0 || serviceIndex >= services.size()) {
            setSpinnerItems(writeSpinner, new String[]{"先连接并选择服务"}, 0);
            setSpinnerItems(notifySpinner, new String[]{"先连接并选择服务"}, 0);
            updateCommunicationControls();
            return;
        }
        ServiceEntry service = services.get(serviceIndex);
        if (CONFIG_SERVICE_UUID.equalsIgnoreCase(service.service.getUuid().toString())) {
            CharacteristicEntry txUuid = findCharacteristic(service, CONFIG_TX_UUID);
            CharacteristicEntry rxUuid = findCharacteristic(service, CONFIG_RX_UUID);
            // 按文档优先 TX 作为 App 发送；若实际属性表明只有 RX 可写，则自动回退。
            CharacteristicEntry writeEntry = supportsWrite(txUuid) ? txUuid
                    : supportsWrite(rxUuid) ? rxUuid
                    : txUuid != null ? txUuid : rxUuid;
            // 按文档优先 RX 作为 App 接收；若实际属性表明只有 TX 可接收，则自动回退。
            CharacteristicEntry receiveEntry = supportsReceive(rxUuid) ? rxUuid
                    : supportsReceive(txUuid) ? txUuid
                    : rxUuid != null ? rxUuid : txUuid;
            if (writeEntry != null) writeOptions.add(writeEntry);
            if (receiveEntry != null) notifyOptions.add(receiveEntry);
        } else {
            for (CharacteristicEntry entry : service.characteristics) {
                if (supportsWrite(entry)) writeOptions.add(entry);
                if (supportsReceive(entry)) notifyOptions.add(entry);
            }
        }
        updatingCharacteristicSpinners = true;
        setSpinnerItems(writeSpinner, labelsFor(writeOptions, false), bestOption(writeOptions, false));
        setSpinnerItems(notifySpinner, labelsFor(notifyOptions, true), bestOption(notifyOptions, true));
        updatingCharacteristicSpinners = false;
        updateCommunicationControls();
    }

    private boolean supportsWrite(CharacteristicEntry entry) {
        if (entry == null) return false;
        int properties = entry.characteristic.getProperties();
        return (properties & (BluetoothGattCharacteristic.PROPERTY_WRITE
                | BluetoothGattCharacteristic.PROPERTY_WRITE_NO_RESPONSE)) != 0;
    }

    private boolean supportsReceive(CharacteristicEntry entry) {
        if (entry == null) return false;
        int properties = entry.characteristic.getProperties();
        return (properties & (BluetoothGattCharacteristic.PROPERTY_NOTIFY
                | BluetoothGattCharacteristic.PROPERTY_INDICATE
                | BluetoothGattCharacteristic.PROPERTY_READ)) != 0;
    }

    private String[] labelsFor(List<CharacteristicEntry> entries, boolean notify) {
        String[] labels = new String[entries.size()];
        for (int i = 0; i < entries.size(); i++) {
            CharacteristicEntry entry = entries.get(i);
            int properties = entry.characteristic.getProperties();
            String capabilities = "";
            if ((properties & BluetoothGattCharacteristic.PROPERTY_WRITE) != 0) capabilities += " WRITE";
            if ((properties & BluetoothGattCharacteristic.PROPERTY_WRITE_NO_RESPONSE) != 0) capabilities += " WNR";
            if ((properties & BluetoothGattCharacteristic.PROPERTY_NOTIFY) != 0) capabilities += " NOTIFY";
            if ((properties & BluetoothGattCharacteristic.PROPERTY_INDICATE) != 0) capabilities += " INDICATE";
            if ((properties & BluetoothGattCharacteristic.PROPERTY_READ) != 0) capabilities += " READ";
            labels[i] = shortUuid(entry.characteristic.getUuid()) + capabilities;
        }
        return labels.length == 0 ? new String[]{notify ? "没有可接收的特征值" : "没有可发送的特征值"} : labels;
    }

    private String propertyLabel(int properties) {
        String value = "";
        if ((properties & BluetoothGattCharacteristic.PROPERTY_WRITE) != 0) value += "WRITE ";
        if ((properties & BluetoothGattCharacteristic.PROPERTY_WRITE_NO_RESPONSE) != 0) value += "WRITE_NO_RESPONSE ";
        if ((properties & BluetoothGattCharacteristic.PROPERTY_NOTIFY) != 0) value += "NOTIFY ";
        if ((properties & BluetoothGattCharacteristic.PROPERTY_INDICATE) != 0) value += "INDICATE ";
        if ((properties & BluetoothGattCharacteristic.PROPERTY_READ) != 0) value += "READ ";
        return value.trim().isEmpty() ? "无可用读写属性" : value.trim();
    }

    private int bestOption(List<CharacteristicEntry> options, boolean notify) {
        // 常见外设命名方向：App 写设备的 RX，订阅设备的 TX。
        String configPreferred = notify ? CONFIG_TX_UUID : CONFIG_RX_UUID;
        String configFallback = notify ? CONFIG_RX_UUID : CONFIG_TX_UUID;
        for (int i = 0; i < options.size(); i++) {
            if (options.get(i).characteristic.getUuid().toString().equalsIgnoreCase(configPreferred)) return i;
        }
        for (int i = 0; i < options.size(); i++) {
            if (options.get(i).characteristic.getUuid().toString().equalsIgnoreCase(configFallback)) return i;
        }
        String preferred = notify ? NORDIC_NOTIFY_UUID : NORDIC_WRITE_UUID;
        for (int i = 0; i < options.size(); i++) {
            String uuid = options.get(i).characteristic.getUuid().toString().toLowerCase(Locale.ROOT);
            if (uuid.contains(preferred) || uuid.contains(UART_TX_UUID)) return i;
        }
        return 0;
    }

    private boolean openCommunicationService() {
        if (!connected || bluetoothGatt == null) {
            toast("请先连接 BLE 设备");
            return false;
        }
        int privateServiceIndex = findPrivateServiceIndex();
        if (privateServiceIndex < 0) {
            privateServiceIndex = loadPrivateServiceDirectly();
        }
        if (privateServiceIndex < 0) {
            try {
                boolean started = bluetoothGatt.discoverServices();
                setStatus(started ? "正在重新发现 GATT 服务…" : "重新发现服务启动失败");
                appendLog(started
                        ? "[系统] 点击服务开关后重新发起 GATT 服务发现。\n"
                        : "[服务错误] 系统拒绝重新发现 GATT 服务。\n");
                toast(started ? "正在读取服务，请稍后再打开" : "未发现私有服务，请重新连接");
            } catch (SecurityException e) {
                toast("缺少蓝牙连接权限");
            }
            return false;
        }
        ServiceEntry privateService = services.get(privateServiceIndex);
        CharacteristicEntry declaredTx = findCharacteristic(privateService, CONFIG_TX_UUID);
        CharacteristicEntry declaredRx = findCharacteristic(privateService, CONFIG_RX_UUID);
        if (declaredTx == null && declaredRx == null) {
            toast("私有服务下没有 TX/RX 特征值");
            appendLog("[服务错误] 已发现私有服务，但没有发现约定的 TX/RX UUID。\n");
            return false;
        }
        updatingCharacteristicSpinners = true;
        serviceSpinner.setSelection(privateServiceIndex);
        updatingCharacteristicSpinners = false;
        updateCharacteristicOptions();
        communicationServiceOpen = true;
        txChannelOpen = false;
        rxChannelOpen = false;
        notificationsEnabled = false;
        syncTxSwitch(false);
        syncRxSwitch(false);
        updateCommunicationControls();
        setStatus("配置服务已打开 · 请分别打开 TX 和 RX");
        appendLog("[服务] 配置服务已打开 " + CONFIG_SERVICE_UUID + "\n");
        appendLog("[服务] TX 声明通道：" + (declaredTx == null ? "未发现" : declaredTx.characteristic.getUuid()
                + " [" + propertyLabel(declaredTx.characteristic.getProperties()) + "]") + "\n");
        appendLog("[服务] RX 声明通道：" + (declaredRx == null ? "未发现" : declaredRx.characteristic.getUuid()
                + " [" + propertyLabel(declaredRx.characteristic.getProperties()) + "]") + "\n");
        toast("服务已打开，请分别开启 TX/RX");
        return true;
    }

    private void closeCommunicationService() {
        closeRxChannel();
        closeTxChannel();
        communicationServiceOpen = false;
        notificationsEnabled = false;
        updateCommunicationControls();
        setStatus("配置服务已停止");
        appendLog("[服务] 配置服务已停止\n");
    }

    private boolean openTxChannel() {
        if (!communicationServiceOpen) {
            toast("请先打开配置服务");
            return false;
        }
        CharacteristicEntry entry = getSelected(writeOptions, writeSpinner);
        if (entry == null) {
            toast("未发现 TX 发送通道");
            appendLog("[TX错误] 私有服务下没有可用发送特征值。\n");
            return false;
        }
        txChannelOpen = true;
        updateCommunicationControls();
        appendLog("[TX] 发送通道已打开：" + entry.characteristic.getUuid()
                + " [" + propertyLabel(entry.characteristic.getProperties()) + "]\n");
        if (!supportsWrite(entry)) appendLog("[TX提示] 固件未声明 WRITE 属性，应用仍会按私有协议尝试写入。\n");
        return true;
    }

    private void closeTxChannel() {
        if (txChannelOpen) appendLog("[TX] 发送通道已关闭\n");
        txChannelOpen = false;
        updateCommunicationControls();
    }

    private boolean openRxChannel() {
        if (!communicationServiceOpen) {
            toast("请先打开配置服务");
            return false;
        }
        CharacteristicEntry entry = getSelected(notifyOptions, notifySpinner);
        if (entry == null) {
            toast("未发现 RX 接收通道");
            appendLog("[RX错误] 私有服务下没有可用接收特征值。\n");
            return false;
        }
        rxChannelOpen = true;
        int properties = entry.characteristic.getProperties();
        boolean canNotify = (properties & (BluetoothGattCharacteristic.PROPERTY_NOTIFY
                | BluetoothGattCharacteristic.PROPERTY_INDICATE)) != 0;
        if (canNotify) enableNotifications(entry, true);
        else if ((properties & BluetoothGattCharacteristic.PROPERTY_READ) != 0) {
            appendLog("[RX] 通道仅支持 READ，将在发送命令后自动读取一次。\n");
        } else {
            appendLog("[RX提示] 固件未声明 NOTIFY/INDICATE/READ，无法保证收到回包。\n");
        }
        updateCommunicationControls();
        appendLog("[RX] 接收通道已打开：" + entry.characteristic.getUuid()
                + " [" + propertyLabel(properties) + "]\n");
        return true;
    }

    private void closeRxChannel() {
        CharacteristicEntry entry = notificationCharacteristic == null
                ? getSelected(notifyOptions, notifySpinner)
                : findCharacteristic(notificationCharacteristic);
        if (rxChannelOpen && entry != null && notificationsEnabled) enableNotifications(entry, false);
        if (rxChannelOpen) appendLog("[RX] 接收通道已关闭\n");
        rxChannelOpen = false;
        notificationsEnabled = false;
        updateCommunicationControls();
    }

    private void setCommunicationServiceOpen(boolean open) {
        communicationServiceOpen = open;
        if (!open) {
            txChannelOpen = false;
            rxChannelOpen = false;
            syncTxSwitch(false);
            syncRxSwitch(false);
        }
        updateCommunicationControls();
    }

    private void updateCommunicationControls() {
        if (sendButton == null) return;
        boolean hasWrite = !writeOptions.isEmpty() && getSelected(writeOptions, writeSpinner) != null;
        boolean hasRead = hasReadableSelectedCharacteristic();
        sendButton.setEnabled(connected && communicationServiceOpen && txChannelOpen && hasWrite);
        if (readButton != null) readButton.setEnabled(connected && communicationServiceOpen && rxChannelOpen && hasRead);
        if (communicationServiceSwitch != null) {
            communicationServiceSwitch.setEnabled(connected);
            syncCommunicationSwitch(communicationServiceOpen);
        }
        if (txChannelSwitch != null) {
            txChannelSwitch.setEnabled(connected && communicationServiceOpen && hasWrite);
            syncTxSwitch(txChannelOpen);
        }
        if (rxChannelSwitch != null) {
            boolean hasReceive = !notifyOptions.isEmpty() && getSelected(notifyOptions, notifySpinner) != null;
            rxChannelSwitch.setEnabled(connected && communicationServiceOpen && hasReceive);
            syncRxSwitch(rxChannelOpen);
        }
        if (communicationStatusView != null) {
            communicationStatusView.setText(communicationServiceOpen ? "配置服务：打开" : "配置服务：关闭");
            communicationStatusView.setTextColor(communicationServiceOpen ? 0xFF087443 : COLOR_TEXT_SECONDARY);
        }
        if (txChannelStatusView != null) {
            txChannelStatusView.setText("TX 发送：" + (txChannelOpen ? "打开" : "关闭") + "\n" + actualWriteUuid());
            txChannelStatusView.setTextColor(txChannelOpen ? 0xFF087443 : COLOR_TEXT_SECONDARY);
        }
        if (rxChannelStatusView != null) {
            rxChannelStatusView.setText("RX 接收：" + (rxChannelOpen ? "打开" : "关闭") + "\n" + actualReceiveUuid());
            rxChannelStatusView.setTextColor(rxChannelOpen ? 0xFF087443 : COLOR_TEXT_SECONDARY);
        }
        if (atChannelStatusView != null) {
            atChannelStatusView.setText("服务：" + onOff(communicationServiceOpen)
                    + "  ·  TX：" + onOff(txChannelOpen) + "  ·  RX：" + onOff(rxChannelOpen));
            atChannelStatusView.setTextColor(communicationServiceOpen && txChannelOpen ? 0xFF087443 : 0xFFC62828);
        }
        if (activationStatusRow != null) {
            boolean privateServiceOpen = communicationServiceOpen
                    && CONFIG_SERVICE_UUID.equalsIgnoreCase(selectedServiceUuid());
            activationStatusRow.setVisibility(privateServiceOpen ? View.VISIBLE : View.GONE);
        }
        updateConnectedHeader();
    }

    private void syncCommunicationSwitch(boolean checked) {
        if (communicationServiceSwitch == null) return;
        updatingCommunicationSwitch = true;
        communicationServiceSwitch.setChecked(checked);
        updatingCommunicationSwitch = false;
    }

    private void syncTxSwitch(boolean checked) {
        if (txChannelSwitch == null) return;
        updatingChannelSwitches = true;
        txChannelSwitch.setChecked(checked);
        updatingChannelSwitches = false;
    }

    private void syncRxSwitch(boolean checked) {
        if (rxChannelSwitch == null) return;
        updatingChannelSwitches = true;
        rxChannelSwitch.setChecked(checked);
        updatingChannelSwitches = false;
    }

    private String onOff(boolean open) { return open ? "开" : "关"; }

    private String actualWriteUuid() {
        CharacteristicEntry entry = getSelected(writeOptions, writeSpinner);
        return entry == null ? CONFIG_TX_UUID : entry.characteristic.getUuid().toString();
    }

    private String actualReceiveUuid() {
        CharacteristicEntry entry = getSelected(notifyOptions, notifySpinner);
        return entry == null ? CONFIG_RX_UUID : entry.characteristic.getUuid().toString();
    }

    private int findPrivateServiceIndex() {
        for (int i = 0; i < services.size(); i++) {
            if (CONFIG_SERVICE_UUID.equalsIgnoreCase(services.get(i).service.getUuid().toString())) return i;
        }
        return -1;
    }

    private int loadPrivateServiceDirectly() {
        if (bluetoothGatt == null) return -1;
        try {
            BluetoothGattService direct = bluetoothGatt.getService(UUID.fromString(CONFIG_SERVICE_UUID));
            if (direct == null) return -1;
            ServiceEntry entry = new ServiceEntry(direct);
            for (BluetoothGattCharacteristic characteristic : direct.getCharacteristics()) {
                entry.characteristics.add(new CharacteristicEntry(direct.getUuid(), characteristic));
            }
            services.add(entry);
            int index = services.size() - 1;
            List<String> labels = new ArrayList<>();
            for (ServiceEntry service : services) {
                labels.add(serviceDisplayName(service.service.getUuid()) + "  ·  " + shortUuid(service.service.getUuid())
                        + (hasWritableCharacteristic(service) ? "  [可写]" : "")
                        + "  ·  " + service.characteristics.size() + " 个特征值");
            }
            updatingCharacteristicSpinners = true;
            setSpinnerItems(serviceSpinner, labels.toArray(new String[0]), index);
            updatingCharacteristicSpinners = false;
            updateCharacteristicOptions();
            updateDiscoveredServicesPanel();
            appendLog("[系统] 已直接从 GATT 缓存读取私有配置服务。\n");
            return index;
        } catch (SecurityException e) {
            return -1;
        }
    }

    private ServiceEntry getSelectedService() {
        int index = serviceSpinner == null ? -1 : serviceSpinner.getSelectedItemPosition();
        return index >= 0 && index < services.size() ? services.get(index) : null;
    }

    private boolean selectedPrivateServiceHasChannel() {
        ServiceEntry service = getSelectedService();
        return service != null
                && CONFIG_SERVICE_UUID.equalsIgnoreCase(service.service.getUuid().toString())
                && (findCharacteristic(service, CONFIG_TX_UUID) != null
                || findCharacteristic(service, CONFIG_RX_UUID) != null);
    }

    private CharacteristicEntry findCharacteristic(ServiceEntry service, String uuid) {
        if (service == null) return null;
        for (CharacteristicEntry entry : service.characteristics) {
            if (entry.characteristic.getUuid().toString().equalsIgnoreCase(uuid)) return entry;
        }
        return null;
    }

    private String selectedServiceUuid() {
        int index = serviceSpinner.getSelectedItemPosition();
        return index >= 0 && index < services.size()
                ? services.get(index).service.getUuid().toString()
                : CONFIG_SERVICE_UUID;
    }

    private boolean hasReadableSelectedCharacteristic() {
        CharacteristicEntry entry = getSelected(notifyOptions, notifySpinner);
        return entry != null && (entry.characteristic.getProperties() & BluetoothGattCharacteristic.PROPERTY_READ) != 0;
    }

    private void readSelectedCharacteristic() {
        if (!connected || !communicationServiceOpen || bluetoothGatt == null) {
            toast("请先打开通信服务");
            return;
        }
        if (!rxChannelOpen) {
            toast("请先打开 RX 接收通道");
            return;
        }
        CharacteristicEntry entry = getSelected(notifyOptions, notifySpinner);
        if (entry == null || (entry.characteristic.getProperties() & BluetoothGattCharacteristic.PROPERTY_READ) == 0) {
            toast("接收特征值不支持 GATT READ");
            appendLog("[读取失败] 选中的接收特征值没有 READ 属性；设备主动上报请使用 Notify/Indicate。\n");
            return;
        }
        try {
            boolean accepted = bluetoothGatt.readCharacteristic(entry.characteristic);
            if (accepted) appendLog("[系统] 正在读取 " + shortUuid(entry.characteristic.getUuid()) + "…\n");
            else appendLog("[读取失败] GATT 正忙或拒绝读取请求\n");
        } catch (SecurityException e) {
            appendLog("[读取失败] 缺少蓝牙连接权限\n");
        }
    }

    private boolean enableNotifications(CharacteristicEntry entry, boolean enabled) {
        if (!connected || bluetoothGatt == null || entry == null) return false;
        BluetoothGattCharacteristic characteristic = entry.characteristic;
        int properties = characteristic.getProperties();
        boolean supportsNotify = (properties & BluetoothGattCharacteristic.PROPERTY_NOTIFY) != 0;
        boolean supportsIndicate = (properties & BluetoothGattCharacteristic.PROPERTY_INDICATE) != 0;
        if (enabled && !supportsNotify && !supportsIndicate) {
            appendLog("[提示] 接收特征值不支持 Notify / Indicate。\n");
            return false;
        }
        byte[] notificationValue = !enabled
                ? BluetoothGattDescriptor.DISABLE_NOTIFICATION_VALUE
                : supportsNotify ? BluetoothGattDescriptor.ENABLE_NOTIFICATION_VALUE
                : BluetoothGattDescriptor.ENABLE_INDICATION_VALUE;
        try {
            bluetoothGatt.setCharacteristicNotification(characteristic, enabled);
            BluetoothGattDescriptor descriptor = characteristic.getDescriptor(CCCD_UUID);
            if (descriptor == null) {
                bluetoothGatt.setCharacteristicNotification(characteristic, false);
                appendLog(enabled ? "[提示] 接收特征值没有 CCCD，无法开启 Notify/Indicate。\n"
                        : "[提示] 没有 CCCD 描述符可关闭通知。\n");
                return false;
            }
            if (Build.VERSION.SDK_INT >= 33) {
                int result = bluetoothGatt.writeDescriptor(descriptor, notificationValue);
                if (result != BluetoothStatusCodes.SUCCESS) {
                    appendLog("[提示] " + (enabled ? "开启" : "关闭") + "接收通知失败，状态=" + result + "\n");
                    return false;
                }
            } else {
                descriptor.setValue(notificationValue);
                if (!bluetoothGatt.writeDescriptor(descriptor)) return false;
            }
            notificationChangePending = true;
            requestedNotificationsEnabled = enabled;
            if (enabled) notificationCharacteristic = characteristic;
            else if (notificationCharacteristic == characteristic) notificationCharacteristic = null;
            appendLog("[系统] 已为 " + shortUuid(characteristic.getUuid())
                    + (enabled ? " 开启接收通知\n" : " 关闭接收通知\n"));
            return enabled;
        } catch (SecurityException e) {
            appendLog("[错误] 缺少蓝牙连接权限，无法" + (enabled ? "开启" : "关闭") + "通知\n");
            return false;
        }
    }

    private void sendCommand() {
        if (!connected || bluetoothGatt == null) {
            toast("请先连接 BLE 设备");
            return;
        }
        if (!communicationServiceOpen) {
            toast("请先打开配置服务");
            return;
        }
        if (!txChannelOpen) {
            toast("请先打开 TX 发送通道");
            return;
        }
        CharacteristicEntry entry = getSelected(writeOptions, writeSpinner);
        if (entry == null && !services.isEmpty()) {
            int automaticService = bestServiceIndex();
            if (hasWritableCharacteristic(services.get(automaticService))) {
                updatingCharacteristicSpinners = true;
                serviceSpinner.setSelection(automaticService);
                updatingCharacteristicSpinners = false;
                updateCharacteristicOptions();
                entry = getSelected(writeOptions, writeSpinner);
                if (entry != null) {
                    appendLog("[系统] 已自动切换到可写服务 "
                            + services.get(automaticService).service.getUuid() + "\n");
                }
            }
        }
        if (entry == null) {
            appendLog("[发送失败] 设备公布的 GATT 服务中没有 WRITE / WRITE_NO_RESPONSE 特征值。\n");
            toast("设备没有可写特征值，请确认 BLE UART 服务");
            return;
        }
        String command = commandInput.getText().toString();
        if (command.isEmpty()) {
            toast("请输入 AT 命令");
            return;
        }
        String normalizedCommand = command.trim().toUpperCase(Locale.ROOT).replace(" ", "");
        pendingActivationCommand = normalizedCommand.startsWith("AT+ACTIVATION_CONTROL")
                ? normalizedCommand
                : "";
        activationResponseBuffer.setLength(0);
        String suffix;
        switch (suffixSpinner.getSelectedItemPosition()) {
            case 1: suffix = "\n"; break;
            case 2: suffix = ""; break;
            default: suffix = "\r\n";
        }
        byte[] payload = (command + suffix).getBytes(StandardCharsets.UTF_8);
        String endingLabel = suffix.isEmpty() ? "" : suffix.equals("\r\n") ? "  [CRLF]" : "  [LF]";
        startWriteSequence(entry.characteristic, payload, command + endingLabel);
    }

    private void startWriteSequence(BluetoothGattCharacteristic characteristic, byte[] payload, String display) {
        if (writeSequenceActive) {
            toast("上一条命令仍在发送，请稍候");
            return;
        }
        int chunkSize = Math.max(20, negotiatedMtu - 3);
        writeChunks.clear();
        for (int offset = 0; offset < payload.length; offset += chunkSize) {
            int length = Math.min(chunkSize, payload.length - offset);
            byte[] chunk = new byte[length];
            System.arraycopy(payload, offset, chunk, 0, length);
            writeChunks.add(chunk);
        }
        if (writeChunks.isEmpty()) writeChunks.add(new byte[0]);
        writeChunkIndex = 0;
        writeSequenceActive = true;
        writeSequenceGeneration++;
        activeWriteCharacteristic = characteristic;
        activeCommandDisplay = display;
        writeFallbackAttempted = false;
        appendLog("[TX] 准备发送 " + payload.length + " 字节，MTU=" + negotiatedMtu
                + "，分为 " + writeChunks.size() + " 包\n");
        sendCurrentChunk();
    }

    private void sendCurrentChunk() {
        if (!writeSequenceActive || writeChunkIndex >= writeChunks.size()) return;
        byte[] chunk = writeChunks.get(writeChunkIndex);
        pendingWritePayload = chunk.clone();
        pendingWriteCharacteristic = activeWriteCharacteristic;
        boolean accepted = writePayload(activeWriteCharacteristic, chunk);
        if (!accepted && !writeFallbackAttempted) {
            accepted = tryAlternatePrivateWrite(activeWriteCharacteristic, chunk);
            if (accepted) activeWriteCharacteristic = pendingWriteCharacteristic;
        }
        if (!accepted) {
            abortWriteSequence("第 " + (writeChunkIndex + 1) + " 包被系统拒绝");
            toast("发送失败，请查看日志");
            return;
        }
        appendLog("[TX] 第 " + (writeChunkIndex + 1) + "/" + writeChunks.size()
                + " 包已提交（" + chunk.length + " 字节）\n");
    }

    private void handleWriteChunkSuccess(BluetoothGattCharacteristic characteristic) {
        if (!writeSequenceActive) return;
        if (activeWriteCharacteristic != null
                && !activeWriteCharacteristic.getUuid().equals(characteristic.getUuid())) return;
        writeChunkIndex++;
        if (writeChunkIndex >= writeChunks.size()) {
            completeWriteSequence();
        } else {
            handler.postDelayed(this::sendCurrentChunk, 25);
        }
    }

    private void completeWriteSequence() {
        appendLog("[TX] " + activeCommandDisplay + " · 发送完成\n");
        writeSequenceActive = false;
        writeChunks.clear();
        pendingWritePayload = new byte[0];
        if (rxChannelOpen && hasReadableSelectedCharacteristic()) {
            handler.postDelayed(this::readSelectedCharacteristic, 250);
        }
    }

    private void abortWriteSequence(String reason) {
        if (reason != null && !reason.isEmpty()) appendLog("[发送失败] " + reason + "\n");
        writeSequenceActive = false;
        writeSequenceGeneration++;
        writeChunks.clear();
        pendingWritePayload = new byte[0];
    }

    private boolean writePayload(BluetoothGattCharacteristic characteristic, byte[] payload) {
        if (bluetoothGatt == null || characteristic == null) return false;
        int properties = characteristic.getProperties();
        int writeType = (properties & BluetoothGattCharacteristic.PROPERTY_WRITE) != 0
                ? BluetoothGattCharacteristic.WRITE_TYPE_DEFAULT
                : BluetoothGattCharacteristic.WRITE_TYPE_NO_RESPONSE;
        try {
            if (Build.VERSION.SDK_INT >= 33) {
                return bluetoothGatt.writeCharacteristic(characteristic, payload, writeType)
                        == BluetoothStatusCodes.SUCCESS;
            }
            characteristic.setWriteType(writeType);
            characteristic.setValue(payload);
            return bluetoothGatt.writeCharacteristic(characteristic);
        } catch (SecurityException e) {
            appendLog("[发送失败] 缺少蓝牙连接权限\n");
            return false;
        }
    }

    private boolean tryAlternatePrivateWrite(BluetoothGattCharacteristic failed, byte[] payload) {
        if (writeFallbackAttempted) return false;
        ServiceEntry service = getSelectedService();
        if (service == null || !CONFIG_SERVICE_UUID.equalsIgnoreCase(service.service.getUuid().toString())) return false;
        CharacteristicEntry tx = findCharacteristic(service, CONFIG_TX_UUID);
        CharacteristicEntry rx = findCharacteristic(service, CONFIG_RX_UUID);
        CharacteristicEntry alternate = tx != null && !tx.characteristic.getUuid().equals(failed.getUuid()) ? tx
                : rx != null && !rx.characteristic.getUuid().equals(failed.getUuid()) ? rx : null;
        if (alternate == null) return false;
        writeFallbackAttempted = true;
        appendLog("[TX] 首选通道被拒绝，尝试备用通道 " + alternate.characteristic.getUuid() + "\n");
        boolean accepted = writePayload(alternate.characteristic, payload);
        if (accepted) {
            pendingWriteCharacteristic = alternate.characteristic;
            writeOptions.clear();
            writeOptions.add(alternate);
            updatingCharacteristicSpinners = true;
            setSpinnerItems(writeSpinner, labelsFor(writeOptions, false), 0);
            updatingCharacteristicSpinners = false;
            updateCommunicationControls();
        }
        return accepted;
    }

    private void receiveBytes(byte[] value) {
        if (value == null || value.length == 0) return;
        String received = new String(value, StandardCharsets.UTF_8);
        runOnUiThread(() -> {
            appendLog("[RX] " + received + (received.endsWith("\n") ? "" : "\n"));
            analyzeActivationResponse(received);
        });
    }

    private void analyzeActivationResponse(String received) {
        activationResponseBuffer.append(received);
        if (activationResponseBuffer.length() > 1024) {
            activationResponseBuffer.delete(0, activationResponseBuffer.length() - 512);
        }
        String response = activationResponseBuffer.toString()
                .replace(" ", "")
                .toUpperCase(Locale.ROOT);
        int onIndex = response.lastIndexOf("+ACTIVATE:ON");
        int offIndex = response.lastIndexOf("+ACTIVATE:OFF");
        if (onIndex >= 0 || offIndex >= 0) {
            setActivationState(onIndex > offIndex);
            pendingActivationCommand = "";
            activationResponseBuffer.setLength(0);
            return;
        }
        if ("AT+ACTIVATION_CONTROL=0".equals(pendingActivationCommand)
                && containsStandaloneOk(response)) {
            setActivationState(false);
            pendingActivationCommand = "";
            activationResponseBuffer.setLength(0);
        }
    }

    private boolean containsStandaloneOk(String response) {
        return response.equals("OK")
                || response.startsWith("OK\r")
                || response.startsWith("OK\n")
                || response.contains("\rOK")
                || response.contains("\nOK");
    }

    private void setActivationState(Boolean active) {
        if (activationStatusView == null) return;
        GradientDrawable background;
        if (active == null) {
            activationStatusView.setText("未知");
            activationStatusView.setTextColor(0xFF687386);
            background = rounded(0xFFE7EBF0, dp(18));
        } else if (active) {
            activationStatusView.setText("已激活");
            activationStatusView.setTextColor(0xFF087443);
            background = rounded(0xFFDDF6E9, dp(18));
        } else {
            activationStatusView.setText("未激活");
            activationStatusView.setTextColor(0xFFC62828);
            background = rounded(0xFFFFE1E1, dp(18));
        }
        activationStatusView.setBackground(background);
    }

    private void disconnectGatt() {
        if (bluetoothGatt == null) return;
        try {
            if (hasBlePermissions()) bluetoothGatt.disconnect();
            else closeGatt(bluetoothGatt);
        } catch (SecurityException e) {
            closeGatt(bluetoothGatt);
        }
    }

    private void closeGatt(BluetoothGatt gatt) {
        try {
            gatt.close();
        } catch (Exception ignored) { }
        if (bluetoothGatt == gatt) bluetoothGatt = null;
        connected = false;
        connecting = false;
        communicationServiceOpen = false;
        notificationsEnabled = false;
        notificationCharacteristic = null;
    }

    private void resetConnectionUi(String message) {
        connectButton.setText("连接所选设备");
        connectButton.setEnabled(selectedDevice != null);
        updatePairButton();
        setCommunicationServiceOpen(false);
        updateCommunicationControls();
        setStatus(message);
    }

    private void stopScan(String reason) {
        handler.removeCallbacks(stopScanRunnable);
        handler.removeCallbacks(deviceListRefreshRunnable);
        deviceListRefreshScheduled = false;
        if (scanning && scanner != null) {
            try {
                scanner.stopScan(scanCallback);
            } catch (SecurityException ignored) { }
        }
        if (scanning) {
            scanning = false;
            if (scanButton != null) scanButton.setText("扫描 BLE");
            if (reason != null && statusView != null) {
                if (devices.isEmpty()) {
                    setStatus("扫描结束 · 0 台设备");
                    appendLog("[扫描提示] 未发现 BLE 广播。MIUI 13 请确认：位置信息总开关已开启、应用定位权限为“使用时允许”、目标设备处于广播/配对模式。\n");
                } else {
                    int visible = visibleDeviceCount();
                    setStatus(reason + " · 发现 " + devices.size() + " 台，显示 " + visible + " 台");
                    if (visible == 0) {
                        appendLog("[过滤提示] 已扫描到 " + devices.size() + " 台 BLE 设备，但没有设备同时满足名称和 MAC 过滤条件。\n");
                    }
                }
            }
        }
        if (deviceListAdapter != null && !deviceListBeingTouched) renderDevices();
    }

    private boolean isLocationServiceEnabled() {
        LocationManager manager = (LocationManager) getSystemService(Context.LOCATION_SERVICE);
        if (manager == null) return false;
        if (Build.VERSION.SDK_INT >= 28) return manager.isLocationEnabled();
        try {
            return manager.isProviderEnabled(LocationManager.GPS_PROVIDER)
                    || manager.isProviderEnabled(LocationManager.NETWORK_PROVIDER);
        } catch (Exception ignored) {
            return false;
        }
    }

    private void showLocationRequiredDialog() {
        setStatus("需要开启系统位置信息才能扫描 BLE");
        new AlertDialog.Builder(this)
                .setTitle("请开启位置信息")
                .setMessage("你的 MIUI / Android 版本要求开启系统“位置信息”总开关，BLE 扫描才会返回设备。这里只用于发现附近的蓝牙设备。")
                .setNegativeButton("取消", null)
                .setPositiveButton("去开启", (dialog, which) -> {
                    try {
                        waitingForLocationEnable = true;
                        startActivity(new Intent(Settings.ACTION_LOCATION_SOURCE_SETTINGS));
                    } catch (Exception e) {
                        waitingForLocationEnable = false;
                        toast("请在系统设置中开启位置信息");
                    }
                })
                .show();
    }

    private void showPermissionRequiredDialog() {
        setStatus("缺少 BLE 扫描所需权限");
        new AlertDialog.Builder(this)
                .setTitle("需要蓝牙扫描权限")
                .setMessage(Build.VERSION.SDK_INT >= 31
                        ? "请在应用权限中同时允许“附近的设备”和“位置信息（仅在使用中）”。MIUI 13 可能同时限制这两项。"
                        : "MIUI 13 扫描 BLE 需要把本应用的定位权限设为“使用应用时允许”。")
                .setNegativeButton("取消", null)
                .setPositiveButton("应用权限", (dialog, which) -> {
                    Intent intent = new Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS,
                            Uri.parse("package:" + getPackageName()));
                    startActivity(intent);
                })
                .show();
    }

    private void registerBondStateReceiver() {
        IntentFilter filter = new IntentFilter(BluetoothDevice.ACTION_BOND_STATE_CHANGED);
        try {
            if (Build.VERSION.SDK_INT >= 33) {
                registerReceiver(bondStateReceiver, filter, Context.RECEIVER_EXPORTED);
            } else {
                registerReceiver(bondStateReceiver, filter);
            }
            bondReceiverRegistered = true;
        } catch (Exception e) {
            appendLog("[提示] 无法监听系统配对状态\n");
        }
    }

    private boolean hasBlePermissions() {
        for (String permission : requiredPermissions()) {
            if (checkSelfPermission(permission) != PackageManager.PERMISSION_GRANTED) return false;
        }
        return true;
    }

    private String[] requiredPermissions() {
        if (Build.VERSION.SDK_INT >= 31) return new String[]{
                Manifest.permission.BLUETOOTH_SCAN,
                Manifest.permission.BLUETOOTH_CONNECT,
                Manifest.permission.ACCESS_FINE_LOCATION,
                Manifest.permission.ACCESS_COARSE_LOCATION
        };
        if (Build.VERSION.SDK_INT >= 23) return new String[]{Manifest.permission.ACCESS_FINE_LOCATION, Manifest.permission.ACCESS_COARSE_LOCATION};
        return new String[0];
    }

    @Override
    public void onRequestPermissionsResult(int requestCode, String[] permissions, int[] grantResults) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults);
        if (requestCode != REQUEST_BLE_PERMISSIONS) return;
        boolean granted = grantResults.length > 0;
        for (int result : grantResults) granted &= result == PackageManager.PERMISSION_GRANTED;
        if (granted) beginScan();
        else showPermissionRequiredDialog();
    }

    @Override
    protected void onResume() {
        super.onResume();
        if (!waitingForLocationEnable) return;
        waitingForLocationEnable = false;
        if (isLocationServiceEnabled()) {
            setStatus("位置信息已开启 · 准备扫描 BLE");
            handler.postDelayed(this::beginScan, 300);
        } else {
            setStatus("位置信息仍未开启，无法扫描 BLE");
        }
    }

    @Override
    protected void onDestroy() {
        handler.removeCallbacks(deviceListRefreshRunnable);
        deviceListRefreshScheduled = false;
        stopScan(null);
        if (bluetoothGatt != null) closeGatt(bluetoothGatt);
        if (bondReceiverRegistered) {
            try {
                unregisterReceiver(bondStateReceiver);
            } catch (Exception ignored) { }
            bondReceiverRegistered = false;
        }
        super.onDestroy();
    }

    private void appendLog(String message) {
        if (logView == null) return;
        String time = new SimpleDateFormat("HH:mm:ss", Locale.getDefault()).format(new Date());
        logView.append("[" + time + "] " + message);
        if (logView.length() > 30_000) logView.setText(logView.getText().subSequence(logView.length() - 24_000, logView.length()));
        logScroll.post(() -> logScroll.fullScroll(View.FOCUS_DOWN));
    }

    private void setStatus(String value) {
        if (statusView != null) statusView.setText(value);
    }

    private String safeAddress(BluetoothDevice device) {
        try { return device.getAddress(); } catch (SecurityException e) { return ""; }
    }

    private String safeName(BluetoothDevice device) {
        try {
            String name = device.getName();
            return name == null || name.isEmpty() ? device.getAddress() : name;
        } catch (SecurityException e) { return "BLE 设备"; }
    }

    private String shortUuid(UUID uuid) {
        String value = uuid.toString().toLowerCase(Locale.ROOT);
        if (value.startsWith("0000") && value.endsWith("-0000-1000-8000-00805f9b34fb")) return value.substring(4, 8);
        return value;
    }

    private void toast(String value) { Toast.makeText(this, value, Toast.LENGTH_SHORT).show(); }

    private TextView text(String value, int size, int color, boolean bold) {
        TextView view = new TextView(this);
        view.setText(value);
        view.setTextSize(size);
        view.setTextColor(color);
        if (bold) view.setTypeface(Typeface.DEFAULT, Typeface.BOLD);
        return view;
    }

    private LinearLayout section(String heading) {
        LinearLayout card = new LinearLayout(this);
        card.setOrientation(LinearLayout.VERTICAL);
        card.setPadding(dp(15), dp(14), dp(15), dp(15));
        card.setBackground(rounded(COLOR_CARD, dp(16)));
        TextView title = text(heading, 16, COLOR_TEXT, true);
        LinearLayout.LayoutParams titleParams = new LinearLayout.LayoutParams(-1, -2);
        titleParams.bottomMargin = dp(12);
        card.addView(title, titleParams);
        return card;
    }

    private LinearLayout horizontal() {
        LinearLayout row = new LinearLayout(this);
        row.setOrientation(LinearLayout.HORIZONTAL);
        row.setGravity(Gravity.CENTER_VERTICAL);
        return row;
    }

    private Button button(String label, int backgroundColor) {
        Button button = new Button(this);
        button.setText(label);
        button.setTextColor(Color.WHITE);
        button.setTextSize(13);
        button.setAllCaps(false);
        button.setMinHeight(dp(42));
        button.setPadding(dp(10), dp(5), dp(10), dp(5));
        button.setBackground(rounded(backgroundColor, dp(10)));
        return button;
    }

    private Spinner spinner() {
        Spinner spinner = new Spinner(this);
        spinner.setBackground(fieldBackground());
        spinner.setPadding(dp(9), 0, dp(9), 0);
        return spinner;
    }

    private EditText filterInput(String hint) {
        EditText input = new EditText(this);
        input.setSingleLine(true);
        input.setTextColor(COLOR_TEXT);
        input.setHintTextColor(0xFF8793A5);
        input.setHint(hint);
        input.setTextSize(14);
        input.setInputType(InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_FLAG_NO_SUGGESTIONS);
        input.setPadding(dp(12), dp(8), dp(12), dp(8));
        input.setBackground(fieldBackground());
        return input;
    }

    private void setSpinnerItems(Spinner spinner, String[] values, int selection) {
        ArrayAdapter<String> adapter = new ArrayAdapter<String>(this, android.R.layout.simple_spinner_item, values) {
            @Override
            public View getView(int position, View convertView, ViewGroup parent) {
                TextView view = (TextView) super.getView(position, convertView, parent);
                view.setTextColor(COLOR_TEXT);
                view.setTextSize(13);
                return view;
            }

            @Override
            public View getDropDownView(int position, View convertView, ViewGroup parent) {
                TextView view = (TextView) super.getDropDownView(position, convertView, parent);
                view.setTextColor(0xFF182235);
                view.setTextSize(14);
                return view;
            }
        };
        adapter.setDropDownViewResource(android.R.layout.simple_spinner_dropdown_item);
        spinner.setAdapter(adapter);
        if (values.length > 0) spinner.setSelection(Math.min(Math.max(selection, 0), values.length - 1));
    }

    private GradientDrawable rounded(int color, int radius) {
        GradientDrawable shape = new GradientDrawable();
        shape.setColor(color);
        shape.setCornerRadius(radius);
        return shape;
    }

    private GradientDrawable fieldBackground() {
        GradientDrawable shape = rounded(Color.WHITE, dp(10));
        shape.setStroke(dp(1), COLOR_BORDER);
        return shape;
    }

    private LinearLayout.LayoutParams sectionParams() {
        LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(-1, -2);
        params.bottomMargin = dp(13);
        return params;
    }

    private LinearLayout.LayoutParams fieldParams() {
        LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(-1, dp(48));
        params.topMargin = dp(6);
        params.bottomMargin = dp(11);
        return params;
    }

    private LinearLayout.LayoutParams compactFieldParams() {
        LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(-1, dp(44));
        params.topMargin = dp(7);
        return params;
    }

    private LinearLayout.LayoutParams weightParams(float weight, int topMargin, int rightMargin) {
        LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(0, dp(44), weight);
        params.topMargin = topMargin;
        params.rightMargin = rightMargin;
        return params;
    }

    private int dp(float value) { return (int) (value * getResources().getDisplayMetrics().density + 0.5f); }

    private CharacteristicEntry findCharacteristic(BluetoothGattCharacteristic characteristic) {
        if (characteristic == null) return null;
        for (ServiceEntry service : services) {
            for (CharacteristicEntry entry : service.characteristics) {
                if (entry.characteristic == characteristic
                        || entry.characteristic.getUuid().equals(characteristic.getUuid())) return entry;
            }
        }
        return null;
    }

    private <T> T getSelected(List<T> values, Spinner spinner) {
        int position = spinner.getSelectedItemPosition();
        return position >= 0 && position < values.size() ? values.get(position) : null;
    }

    private class DeviceListAdapter extends BaseAdapter {
        @Override
        public int getCount() {
            return filteredDeviceIndices.isEmpty() ? 1 : filteredDeviceIndices.size();
        }

        @Override
        public Object getItem(int position) {
            if (filteredDeviceIndices.isEmpty() || position < 0 || position >= filteredDeviceIndices.size()) return null;
            return devices.get(filteredDeviceIndices.get(position));
        }

        @Override
        public long getItemId(int position) {
            if (filteredDeviceIndices.isEmpty() || position < 0 || position >= filteredDeviceIndices.size()) return -1;
            int index = filteredDeviceIndices.get(position);
            return deviceAddresses.get(index).toLowerCase(Locale.ROOT).hashCode();
        }

        @Override
        public boolean hasStableIds() {
            return true;
        }

        @Override
        public boolean isEnabled(int position) {
            return !filteredDeviceIndices.isEmpty();
        }

        @Override
        public View getView(int position, View convertView, ViewGroup parent) {
            TextView row = convertView instanceof TextView ? (TextView) convertView : new TextView(MainActivity.this);
            row.setGravity(Gravity.START | Gravity.CENTER_VERTICAL);
            row.setSingleLine(false);
            row.setMinHeight(dp(50));
            row.setTextSize(12);
            row.setPadding(dp(12), dp(6), dp(12), dp(6));

            if (filteredDeviceIndices.isEmpty()) {
                row.setText(deviceRows.isEmpty()
                        ? "还没有设备。请点击“扫描 BLE”。"
                        : "已发现设备，但没有同时匹配名称和 MAC 过滤条件的结果。");
                row.setTextColor(deviceRows.isEmpty() ? COLOR_TEXT_SECONDARY : 0xFFB26100);
                row.setBackgroundColor(Color.TRANSPARENT);
                return row;
            }

            int index = filteredDeviceIndices.get(position);
            BluetoothDevice device = devices.get(index);
            boolean selected = selectedDevice != null && sameDevice(selectedDevice, device);
            String rowText = deviceRows.get(index) + "  ·  " + bondStateLabel(device);
            if (isGattConnectedDevice(device)) rowText += "  ·  已连接";
            row.setText(rowText);
            row.setTextColor(selected ? Color.WHITE : COLOR_TEXT);
            row.setBackground(rounded(selected ? COLOR_TEAL : 0xFFE7EDF4, dp(10)));
            return row;
        }
    }

    private class ServiceEntry {
        final BluetoothGattService service;
        final List<CharacteristicEntry> characteristics = new ArrayList<>();
        ServiceEntry(BluetoothGattService service) { this.service = service; }
    }

    private static class CharacteristicEntry {
        final UUID serviceUuid;
        final BluetoothGattCharacteristic characteristic;
        CharacteristicEntry(UUID serviceUuid, BluetoothGattCharacteristic characteristic) {
            this.serviceUuid = serviceUuid;
            this.characteristic = characteristic;
        }
    }

    private interface ItemSelectedAction { void onSelected(int position); }

    private static class SimpleItemSelectedListener implements android.widget.AdapterView.OnItemSelectedListener {
        private final ItemSelectedAction action;
        SimpleItemSelectedListener(ItemSelectedAction action) { this.action = action; }
        @Override public void onItemSelected(android.widget.AdapterView<?> parent, View view, int position, long id) { action.onSelected(position); }
        @Override public void onNothingSelected(android.widget.AdapterView<?> parent) { }
    }
}
