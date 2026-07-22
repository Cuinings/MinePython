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
        btn_dl:"下载",btn_del:"删除",btn_preview:"预览",prompt_cat:"输入新分类名称:",
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
        audit_scope_all:"全部用户",audit_scope_self:"仅本人",audit_filter_user:"筛选用户",audit_search_ph:"搜索目标…",
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
        btn_dl:"DL",btn_del:"Del",btn_preview:"Preview",prompt_cat:"Category name:",
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
        audit_scope_all:"All users",audit_scope_self:"Only me",audit_filter_user:"Filter user",audit_search_ph:"Search target…",
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
        btn_dl:"Скачать",btn_del:"Удалить",btn_preview:"Предпросмотр",prompt_cat:"Название категории:",
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
        audit_scope_all:"Все",audit_scope_self:"Только я",audit_filter_user:"Пользователь",audit_search_ph:"Поиск цели…",
    }
};

var LANGS = ['zh','en','ru'];
var LANG_LABELS = {zh:'中',en:'EN',ru:'RU'};
var LANG_NAMES = {zh:'中文',en:'English',ru:'Русский'};
var lang = localStorage.getItem('fs_lang') || 'zh';

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
