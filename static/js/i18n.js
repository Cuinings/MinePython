// =====================================================================
//  File Server — i18n (zh / en / ru) + language switching (P2-3)
//  Classic script: keeps I18N / t() / applyI18n() on the global scope so the
//  per-page inline scripts and other modules can call them directly.
// =====================================================================

var I18N = {
    zh: {
        title:"MinePython",h1:"📁 MinePython",subtitle_label:"分类管理",
        loading:"加载中...",login_required:"登录已失效，请重新登录",auto_tag:"🤖 自动归类",new_tag:"+ 新建",
        del_title:"删除分类",btn_organize:"🗂 整理归类",
        organize_title:"将根目录散落文件按类型归类",
        upload_title:"点击或拖拽文件到此处上传",upload_desc:"支持任意文件类型，可批量上传",
        upload_entry:"上传文件",
        hint_auto:"上传模式: 🤖 自动归类（根据文件类型）",hint_target:"上传到: ",
        all_files:"全部文件",cat_label:"分类: ",no_files:"暂无文件",view_cat:"查看该分类",
        btn_dl:"下载",btn_del:"删除",btn_preview:"预览",preview_unsupported:"该文件类型无法在线预览，请下载",prompt_cat:"输入新分类名称:",
        confirm_del_cat:"确定删除分类",and_all_files:"及其下所有文件？",
        confirm_del_file:"确定删除",confirm_organize:"将根目录散落文件按类型归类？",
        toast_deleted:"已删除",toast_failed:"失败",toast_del_failed:"删除失败",
        toast_upload_ok:"已上传 → ",toast_upload_fail:"上传失败",
        toast_organized:"已整理",files_suffix:" 个文件",toast_organize_fail:"整理失败",
        auto_label:"自动归类",login:"登录",register:"注册",logout:"退出",nav_files:"文件",nav_users:"用户管理",home_files_desc:"上传、浏览、搜索、下载与管理文件",home_users_desc:"审批注册申请、管理账号与权限",back_home:"← 返回首页",
        select_all:"全选",batch_dl:"批量下载",batch_approve:"批量通过",batch_reject:"批量拒绝",
        batch_delete:"批量删除",batch_done:"已处理 {n} 项",batch_dl_done:"已开始打包下载",
        confirm_batch:"确认对选中的 {n} 项执行「{act}」？",
        login_sub:"登录以继续",register_sub:"注册新账号",
        username_ph:"用户名",password_ph:"密码",
        no_account:"没有账号? 注册",has_account:"已有账号? 登录",
        skip_login:"跳过, 以匿名身份进入",
        back_files:"← 返回文件浏览",anonymous:"匿名",
        pending_approval:"注册已提交, 等待管理员审批",
        user_mgmt:"用户管理",pending:"待审批",active:"已激活",
        approve:"通过",reject:"拒绝",confirm_reject:"确定拒绝该用户的注册申请（账户将被禁用）？",
        no_users:"暂无用户",fill_fields:"请填写所有字段",net_error:"网络错误",
        register_sub:"注册新账号",login_sub:"登录以继续",
        pending_alert:"待审批用户",view_approvals:"查看审批",
        detail_name:"文件名",detail_category:"分类",detail_path:"路径",
        detail_size:"大小",detail_uploader:"上传者",detail_ip:"上传IP",
        detail_time:"上传时间",
        nickname_label:"昵称",password_label:"密码",
        btn_add_user:"+ 添加用户",btn_edit:"编辑",btn_save:"保存",btn_cancel:"取消",
        change_pw:"修改密码",deactivate:"注销账号",change_pw_title:"修改密码",
        old_pw:"当前密码",new_pw:"新密码",confirm_pw:"确认新密码",
        pw_mismatch:"两次输入的新密码不一致",deactivate_confirm:"注销后账号将无法登录，确定继续？",
        pw_changed_relogin:"密码已修改，请重新登录",acct_deactivated:"账号已注销",
        role_label:"角色",status_label:"状态",
        modal_add_title:"添加用户",modal_edit_title:"编辑用户",
        click_show_pw:"点击显示密码",click_hide_pw:"点击隐藏密码",
        tab_users:"用户管理",tab_audit:"审计日志",
        audit_title:"审计日志",audit_desc:"操作记录与安全审计",
        audit_time:"时间",audit_user:"操作用户",audit_action:"动作",
        audit_target:"目标",audit_ip:"来源IP",audit_refresh:"刷新",
        audit_export:"导出CSV",audit_limit:"条数",no_audit:"暂无审计记录",
        nav_audit:"审计日志",home_audit_desc:"查看本人操作记录与安全审计（管理员可见全部）",
        audit_self_note:"仅显示本人操作记录（管理员可查看全部）",
        audit_scope_all:"全部用户",audit_scope_self:"仅本人",audit_filter_user:"筛选用户",        audit_search_ph:"搜索目标…",
        site_settings:"站点设置",site_name:"站点名称",site_save:"保存",
        site_saved:"已保存，新名称将在全局刷新后生效",site_name_ph:"请输入站点名称",
        ucenter:"用户中心",user_info:"用户信息",settings:"设置",home_settings_desc:"个性化与系统偏好设置",center_desc:"查看并管理你的账号",edit_profile:"修改资料",logout_login:"退出登陆",ui_username:"用户名",ui_nickname:"昵称",ui_role:"角色",ui_status:"状态",ui_permissions:"权限",ui_ip:"登录IP",profile_saved:"资料已更新",profile_nick_ph:"请输入昵称",settings_blank:"（设置模块开发中，敬请期待）",
        btn_adb_install:"ADB安装",adb_title:"通过 ADB 安装",adb_scanning:"正在扫描设备…",adb_choose:"选择目标设备",adb_no_device:"未检测到已连接且已授权的设备，请连接手机并开启 USB 调试。",adb_installing:"正在安装，请稍候…",adb_success:"安装成功",adb_fail:"安装失败",adb_close:"关闭",adb_no_adb:"未检测到 adb：请先安装 Android SDK Platform-Tools 并加入 PATH，或在 .env 中设置 ADB_PATH。",adb_unauthorized:"设备未授权（请在手机上允许 USB 调试）。",adb_output:"安装日志",adb_need_https:"WebUSB 需要安全上下文（HTTPS）。请通过 https 打开本页面（例如 https://服务器地址:8000/files.html），http 下浏览器会禁用设备连接。",adb_need_browser:"当前浏览器不支持 WebUSB。请使用 Chrome / Edge / Brave 等基于 Chromium 的浏览器打开本页面。",adb_guide_webusb_intro:"安装完全在你的浏览器里通过 WebUSB 直连手机完成，服务器不需要安装 adb。请按以下步骤准备：",adb_w1:"用 Chrome / Edge 打开本页",adb_w2:"手机开启 USB 调试",adb_w3:"连接并授权",adb_w4:"重新点击安装",adb_retry:"重新安装",adb_connecting:"正在连接设备（请在浏览器弹窗中选择手机并允许）…",adb_downloading:"正在从服务器下载 APK…",adb_lib_fail:"ADB 库加载失败：缺少 Adb / AdbDaemonWebUsbDeviceManager / AdbWebCredentialStore",adb_lib_fail_hint:"请先在服务器运行 \"python download_webadb2.py\"，然后完全重启服务器再试。",adb_dl_fail:"APK 下载失败",adb_install_fail:"安装失败",adb_usb_denied:"未选择设备或已取消，请在浏览器弹窗中允许访问手机 USB 后重试。",adb_guide_btn:"查看配置指引",adb_guide_intro:"本服务的运行机器上需要安装 adb（Android 调试桥）。如果你通过服务器 / 容器访问，请在「运行本服务的那台机器」上安装，并把手机用数据线连到它。装好后点「重新检测」。",adb_s1_dl:"下载 Android SDK Platform-Tools",adb_s2_extract:"解压到本地目录",adb_s3_path:"加入 PATH 或设置 ADB_PATH",adb_s4_verify:"验证安装",adb_s5_phone:"手机开启 USB 调试并连接本机",adb_s6_rescan:"回到本页重新检测",adb_rescan:"重新检测",
    },
    en: {
        title:"MinePython",h1:"📁 MinePython",subtitle_label:"Categories",
        loading:"Loading...",login_required:"Session expired, please log in again",auto_tag:"🤖 Auto",new_tag:"+ New",
        del_title:"Delete category",btn_organize:"🗂 Organize",
        organize_title:"Move root files into category folders",
        upload_title:"Click or drag files here to upload",upload_desc:"Supports any file type, batch upload",
        upload_entry:"Upload Files",
        hint_auto:"Mode: 🤖 Auto-detect (by file extension)",hint_target:"Target: ",
        all_files:"All Files",cat_label:"Category: ",no_files:"No files",view_cat:"View this category",
        btn_dl:"DL",btn_del:"Del",btn_preview:"Preview",preview_unsupported:"This file type cannot be previewed online. Please download.",prompt_cat:"Category name:",
        confirm_del_cat:"Delete category \"",and_all_files:"\" and all files?",
        confirm_del_file:"Delete \"",confirm_organize:"Move root files into category folders?",
        toast_deleted:"Deleted",toast_failed:"Failed",toast_del_failed:"Delete failed",
        toast_upload_ok:"Uploaded -> ",toast_upload_fail:"Upload failed",
        toast_organized:"Organized ",files_suffix:" file(s)",toast_organize_fail:"Organize failed",
        auto_label:"auto",login:"Login",register:"Register",logout:"Logout",nav_files:"Files",nav_users:"User Management",home_files_desc:"Upload, browse, search, download and manage files",home_users_desc:"Approve sign-ups and manage accounts & roles",back_home:"← Back to Home",
        select_all:"Select all",batch_dl:"Batch Download",batch_approve:"Batch Approve",batch_reject:"Batch Reject",
        batch_delete:"Batch Delete",batch_done:"Processed {n} item(s)",batch_dl_done:"Packing download...",
        confirm_batch:"Apply '{act}' to the selected {n} item(s)?",
        login_sub:"Login to continue",register_sub:"Create new account",
        username_ph:"Username",password_ph:"Password",
        no_account:"No account? Register",has_account:"Have account? Login",
        skip_login:"Skip, enter as anonymous",
        back_files:"← Back to files",anonymous:"anonymous",
        pending_approval:"Registration submitted, pending admin approval",
        user_mgmt:"User Management",pending:"pending",active:"active",
        approve:"Approve",reject:"Reject",confirm_reject:"Reject this user's registration (account will be disabled)?",
        no_users:"No users",fill_fields:"Fill all fields",net_error:"Network error",
        register_sub:"Create new account",login_sub:"Login to continue",
        pending_alert:"Pending approvals",view_approvals:"Review",
        detail_name:"Filename",detail_category:"Category",detail_path:"Path",
        detail_size:"Size",detail_uploader:"Uploader",detail_ip:"Upload IP",
        detail_time:"Upload Time",
        nickname_label:"Nickname",password_label:"Password",
        btn_add_user:"+ Add User",btn_edit:"Edit",btn_save:"Save",btn_cancel:"Cancel",
        change_pw:"Change Password",deactivate:"Deactivate",change_pw_title:"Change Password",
        old_pw:"Current Password",new_pw:"New Password",confirm_pw:"Confirm New Password",
        pw_mismatch:"New passwords do not match",deactivate_confirm:"Deactivating will disable login. Continue?",
        pw_changed_relogin:"Password changed, please log in again",acct_deactivated:"Account deactivated",
        role_label:"Role",status_label:"Status",
        modal_add_title:"Add User",modal_edit_title:"Edit User",
        click_show_pw:"Click to show password",click_hide_pw:"Click to hide password",
        tab_users:"User Management",tab_audit:"Audit Log",
        audit_title:"Audit Log",audit_desc:"Operation & security audit trail",
        audit_time:"Time",audit_user:"User",audit_action:"Action",
        audit_target:"Target",audit_ip:"Source IP",audit_refresh:"Refresh",
        audit_export:"Export CSV",audit_limit:"Rows",no_audit:"No audit records",
        nav_audit:"Audit Log",home_audit_desc:"View your own operations & security audit (admins see all)",
        audit_self_note:"Showing your own records only (admins can view all)",
        audit_scope_all:"All users",audit_scope_self:"Only me",audit_filter_user:"Filter user",        audit_search_ph:"Search target…",
        site_settings:"Site Settings",site_name:"Site name",site_save:"Save",
        site_saved:"Saved. New name applies site-wide after refresh.",site_name_ph:"Enter the site name",
        ucenter:"User Center",user_info:"User Info",settings:"Settings",home_settings_desc:"Personalization & system preferences",center_desc:"View and manage your account",edit_profile:"Edit Profile",logout_login:"Log Out",ui_username:"Username",ui_nickname:"Nickname",ui_role:"Role",ui_status:"Status",ui_permissions:"Permissions",ui_ip:"Login IP",profile_saved:"Profile updated",profile_nick_ph:"Enter nickname",settings_blank:"(Settings module coming soon)",
        btn_adb_install:"ADB Install",adb_title:"Install via ADB",adb_scanning:"Scanning devices…",adb_choose:"Choose a device",adb_no_device:"No connected & authorized device found. Connect a phone and enable USB debugging.",adb_installing:"Installing, please wait…",adb_success:"Installed successfully",adb_fail:"Installation failed",adb_close:"Close",adb_no_adb:"adb not found: install Android SDK Platform-Tools and add it to PATH, or set ADB_PATH in .env.",adb_unauthorized:"Device not authorized (allow USB debugging on the phone).",adb_output:"Install log",adb_need_https:"WebUSB needs a secure context (HTTPS). Open this page over https (e.g. https://server:8000/files.html); browsers block device access over http.",adb_need_browser:"This browser does not support WebUSB. Use a Chromium-based browser such as Chrome / Edge / Brave.",adb_guide_webusb_intro:"Installation runs entirely in your browser over WebUSB, connecting directly to the phone — the server does not need adb. Prepare as follows:",adb_w1:"Open this page in Chrome / Edge",adb_w2:"Enable USB debugging on the phone",adb_w3:"Connect & authorize",adb_w4:"Click install again",adb_retry:"Retry install",adb_connecting:"Connecting to device (pick your phone in the browser prompt and allow)…",adb_downloading:"Downloading APK from server…",adb_lib_fail:"ADB library failed to load: missing Adb / AdbDaemonWebUsbDeviceManager / AdbWebCredentialStore",adb_lib_fail_hint:"Run \"python download_webadb2.py\" on the server, then fully restart the server and retry.",adb_dl_fail:"APK download failed",adb_install_fail:"Installation failed",adb_usb_denied:"No device selected or cancelled — allow the browser USB access and retry.",adb_guide_btn:"Setup guide",adb_guide_intro:"adb (Android Debug Bridge) must be installed on the MACHINE RUNNING THIS SERVICE. If you access it via a server/container, install adb there and connect the phone to that machine with a USB cable. Then click “Re-detect”.",adb_s1_dl:"Download Android SDK Platform-Tools",adb_s2_extract:"Extract to a local folder",adb_s3_path:"Add to PATH or set ADB_PATH",adb_s4_verify:"Verify the install",adb_s5_phone:"Enable USB debugging & connect the phone",adb_s6_rescan:"Return here and re-detect",adb_rescan:"Re-detect",
    },
    ru: {
        title:"MinePython",h1:"📁 MinePython",subtitle_label:"Категории",
        loading:"Загрузка...",login_required:"Сессия истекла, войдите снова",auto_tag:"🤖 Авто",new_tag:"+ Новый",
        del_title:"Удалить категорию",btn_organize:"🗂 Упорядочить",
        organize_title:"Переместить корневые файлы в папки категорий",
        upload_title:"Нажмите или перетащите файлы для загрузки",
        upload_desc:"Поддерживаются любые типы файлов",upload_entry:"Загрузить файлы",
        hint_auto:"Режим: 🤖 Автоопределение (по расширению)",hint_target:"Цель: ",
        all_files:"Все файлы",cat_label:"Категория: ",no_files:"Нет файлов",view_cat:"Просмотр категории",
        btn_dl:"Скачать",btn_del:"Удалить",btn_preview:"Предпросмотр",preview_unsupported:"Этот тип файла нельзя просмотреть онлайн. Скачайте файл.",prompt_cat:"Название категории:",
        confirm_del_cat:"Удалить категорию \"",and_all_files:"\" и все файлы?",
        confirm_del_file:"Удалить \"",confirm_organize:"Переместить корневые файлы в папки категорий?",
        toast_deleted:"Удалено",toast_failed:"Ошибка",toast_del_failed:"Ошибка удаления",
        toast_upload_ok:"Загружено → ",toast_upload_fail:"Ошибка загрузки",
        toast_organized:"Упорядочено ",files_suffix:" файл(ов)",toast_organize_fail:"Ошибка упорядочивания",
        auto_label:"авто",login:"Войти",register:"Регистрация",logout:"Выйти",nav_files:"Файлы",nav_users:"Управление пользователями",home_files_desc:"Загрузка, просмотр, поиск и управление файлами",home_users_desc:"Одобрение заявок и управление аккаунтами",back_home:"← На главную",
        select_all:"Выбрать все",batch_dl:"Скачать всё",batch_approve:"Пакетное одобр.",batch_reject:"Пакетное откл.",
        batch_delete:"Пакетное удал.",batch_done:"Обработано {n}",batch_dl_done:"Упаковка...",
        confirm_batch:"Применить «{act}» к выбранным {n}?",
        login_sub:"Войдите для продолжения",register_sub:"Создать аккаунт",
        username_ph:"Имя пользователя",password_ph:"Пароль",
        no_account:"Нет аккаунта? Регистрация",has_account:"Есть аккаунт? Войти",
        skip_login:"Пропустить, войти анонимно",
        back_files:"← Назад к файлам",anonymous:"аноним",
        pending_approval:"Регистрация отправлена, ожидает одобрения",
        user_mgmt:"Управление пользователями",pending:"ожидание",active:"активен",
        approve:"Одобрить",reject:"Отклонить",confirm_reject:"Отклонить регистрацию (аккаунт будет отключён)?",
        no_users:"Нет пользователей",fill_fields:"Заполните все поля",net_error:"Ошибка сети",
        register_sub:"Создать аккаунт",login_sub:"Войдите для продолжения",
        pending_alert:"Новые заявки",view_approvals:"Обзор",
        detail_name:"Имя файла",detail_category:"Категория",detail_path:"Путь",
        detail_size:"Размер",detail_uploader:"Загрузчик",detail_ip:"IP",
        detail_time:"Время",
        nickname_label:"Псевдоним",password_label:"Пароль",
        btn_add_user:"+ Добавить",btn_edit:"Ред.",btn_save:"Сохранить",btn_cancel:"Отмена",
        change_pw:"Сменить пароль",deactivate:"Удалить аккаунт",change_pw_title:"Смена пароля",
        old_pw:"Текущий пароль",new_pw:"Новый пароль",confirm_pw:"Подтвердите пароль",
        pw_mismatch:"Пароли не совпадают",deactivate_confirm:"После удаления вход будет невозможен. Продолжить?",
        pw_changed_relogin:"Пароль изменён, войдите снова",acct_deactivated:"Аккаунт удалён",
        role_label:"Роль",status_label:"Статус",
        modal_add_title:"Добавить",modal_edit_title:"Изменить",
        click_show_pw:"Показать пароль",click_hide_pw:"Скрыть пароль",
        tab_users:"Пользователи",tab_audit:"Журнал",
        audit_title:"Журнал аудита",audit_desc:"Журнал операций и безопасности",
        audit_time:"Время",audit_user:"Пользователь",audit_action:"Действие",
        audit_target:"Цель",audit_ip:"IP",audit_refresh:"Обновить",
        audit_export:"Экспорт CSV",audit_limit:"Строк",no_audit:"Нет записей",
        nav_audit:"Журнал",home_audit_desc:"Ваши операции и аудит безопасности (админ — все)",
        audit_self_note:"Только ваши записи (админ видит все)",
        audit_scope_all:"Все",audit_scope_self:"Только я",audit_filter_user:"Пользователь",        audit_search_ph:"Поиск цели…",
        site_settings:"Настройки сайта",site_name:"Название сайта",site_save:"Сохранить",
        site_saved:"Сохранено. Новое имя применится после обновления.",site_name_ph:"Введите название сайта",
        ucenter:"Центр пользователя",user_info:"Информация",settings:"Настройки",home_settings_desc:"Персонализация и настройки системы",center_desc:"Просмотр и управление аккаунтом",edit_profile:"Изменить профиль",logout_login:"Выйти",ui_username:"Имя",ui_nickname:"Псевдоним",ui_role:"Роль",ui_status:"Статус",ui_permissions:"Права",ui_ip:"IP входа",profile_saved:"Профиль обновлён",profile_nick_ph:"Введите псевдоним",settings_blank:"(Модуль настроек скоро)",
        btn_adb_install:"ADB",adb_title:"Установка через ADB",adb_scanning:"Поиск устройств…",adb_choose:"Выберите устройство",adb_no_device:"Подключённое и авторизованное устройство не найдено. Включите USB-отладку.",adb_installing:"Установка, подождите…",adb_success:"Успешно установлено",adb_fail:"Ошибка установки",adb_close:"Закрыть",adb_no_adb:"adb не найден: установите Android SDK Platform-Tools и добавьте в PATH или задайте ADB_PATH.",adb_unauthorized:"Устройство не авторизовано (разрешите USB-отладку).",adb_output:"Журнал установки",adb_need_https:"WebUSB требует защищённого контекста (HTTPS). Откройте страницу по https (например https://сервер:8000/files.html); по http браузер блокирует доступ к устройству.",adb_need_browser:"Этот браузер не поддерживает WebUSB. Используйте Chromium-браузер (Chrome / Edge / Brave).",adb_guide_webusb_intro:"Установка выполняется полностью в браузере через WebUSB напрямую в телефон — серверу не нужен adb. Подготовьте:",adb_w1:"Откройте страницу в Chrome / Edge",adb_w2:"Включите USB-отладку на телефоне",adb_w3:"Подключите и разрешите",adb_w4:"Нажмите установить снова",adb_retry:"Повторить установку",adb_connecting:"Подключение к устройству (выберите телефон в окне браузера и разрешите)…",adb_downloading:"Загрузка APK с сервера…",adb_lib_fail:"Ошибка загрузки библиотеки ADB: нет Adb / AdbDaemonWebUsbDeviceManager / AdbWebCredentialStore",adb_lib_fail_hint:"Запустите \"python download_webadb2.py\" на сервере, полностью перезапустите сервер и повторите попытку.",adb_dl_fail:"Ошибка загрузки APK",adb_install_fail:"Ошибка установки",adb_usb_denied:"Устройство не выбрано или отменено — разрешите браузеру USB-доступ и повторите.",adb_guide_btn:"Инструкция",adb_guide_intro:"adb (Android Debug Bridge) должен быть установлен на МАШИНЕ, ГДЕ РАБОТАЕТ ЭТОТ СЕРВИС. При доступе через сервер/контейнер — установите adb там и подключите телефон по USB к той машине. Затем нажмите «Повторить».",adb_s1_dl:"Скачать Android SDK Platform-Tools",adb_s2_extract:"Распаковать в папку",adb_s3_path:"Добавить в PATH или задать ADB_PATH",adb_s4_verify:"Проверить установку",adb_s5_phone:"Включите USB-отладку и подключите телефон",adb_s6_rescan:"Вернитесь сюда и повторите",adb_rescan:"Повторить",
    }
};

var LANGS = ['zh','en','ru'];
var LANG_LABELS = {zh:'中',en:'EN',ru:'RU'};
var LANG_NAMES = {zh:'中文',en:'English',ru:'Русский'};
var lang = localStorage.getItem('fs_lang') || 'zh';

// ---------------------------------------------------------------------
// 工程名（动态自定义）：后端由 APP_NAME 环境变量决定，前端启动时拉取
// /api/app-info 并把三语的 title / h1 替换为实际名字，再重新渲染。
// HTML 里写死的 "MinePython" 只作为拉取前的默认占位。
// ---------------------------------------------------------------------
var APP_NAME = 'MinePython';

function setAppName(name) {
    if (!name) return;
    APP_NAME = name;
    LANGS.forEach(function(code) {
        if (I18N[code]) {
            I18N[code].title = name;
            I18N[code].h1 = '📁 ' + name;
        }
    });
    if (typeof applyI18n === 'function') applyI18n();
}

function loadAppName() {
    fetch('/api/app-info')
        .then(function(r) { return r.ok ? r.json() : null; })
        .then(function(d) { if (d && d.name) setAppName(d.name); })
        .catch(function() {});
}

loadAppName();

function t(key) {
    var m = I18N[lang];
    return m && m[key] !== undefined ? m[key] : key;
}

function toggleLangMenu(e) {
    e.stopPropagation();
    var menu = document.getElementById('langMenu');
    if (menu) menu.classList.toggle('show');
}

function switchToLang(code) {
    if (lang === code) { var m = document.getElementById('langMenu'); if (m) m.classList.remove('show'); return; }
    lang = code;
    localStorage.setItem('fs_lang', lang);
    applyI18n();
    updateLangBtn();
    if (typeof updateUploadHint === 'function') updateUploadHint();
    if (typeof refreshUI === 'function') refreshUI();
    var menu = document.getElementById('langMenu');
    if (menu) menu.classList.remove('show');
}

function updateLangBtn() {
    var btn = document.getElementById('langBtn');
    if (btn) btn.textContent = LANG_LABELS[lang];
    document.querySelectorAll('.lang-menu-item').forEach(function(el) {
        el.classList.toggle('active', el.dataset.lang === lang);
    });
}

function applyI18n() {
    document.querySelectorAll('[data-i18n]').forEach(function(el) {
        var k = el.dataset.i18n;
        if (k) el.textContent = t(k);
    });
    document.querySelectorAll('[data-i18n-title]').forEach(function(el) {
        var k = el.dataset.i18nTitle;
        if (k) el.title = t(k);
    });
    document.querySelectorAll('[data-i18n-placeholder]').forEach(function(el) {
        var k = el.dataset.i18nPlaceholder;
        if (k) el.placeholder = t(k);
    });
    document.title = t('title');
}

// Pages may override refreshUI() for language-switch refresh.
function refreshUI() {}
