<?php
/**
 * Plugin Name: CrapScraper Manual Update
 * Description: Fila atualizações seguras de Plugin, Tema e Template para o CrapScraper local.
 * Version: 2.4.0
 */
defined('ABSPATH') || exit;

final class CrapScraper_Manual_Update {
    const NONCE_ACTION = 'crapscraper_manual_update';
    const DB_VERSION = '2.4.0';

    public static function init() {
        self::ensure_table();
        add_action('add_meta_boxes_product', array(__CLASS__, 'add_meta_box'));
        add_action('admin_enqueue_scripts', array(__CLASS__, 'assets'));
        add_action('wp_enqueue_scripts', array(__CLASS__, 'frontend_assets'));
        add_action('wp_footer', array(__CLASS__, 'render_frontend'));
        add_action('template_redirect', array(__CLASS__, 'frontend_no_cache'));
        add_action('wp_ajax_crapscraper_manual_start', array(__CLASS__, 'ajax_start'));
        add_action('wp_ajax_crapscraper_manual_status', array(__CLASS__, 'ajax_status'));
        add_action('wp_ajax_crapscraper_manual_history', array(__CLASS__, 'ajax_history'));
        add_action('rest_api_init', array(__CLASS__, 'rest_routes'));
        add_filter('rest_pre_serve_request', array(__CLASS__, 'rest_no_cache'), 10, 4);
    }

    private static function table() { global $wpdb; return $wpdb->prefix . 'crapscraper_manual_updates'; }
    private static function authorized() { return is_user_logged_in() && is_super_admin(get_current_user_id()); }

    private static function eligible($product_id) {
        if ('product' !== get_post_type($product_id)) return false;
        $terms = wp_get_post_terms($product_id, 'product_cat', array('fields' => 'all'));
        if (is_wp_error($terms)) return false;
        foreach ($terms as $term) {
            $value = remove_accents(strtolower($term->slug . ' ' . $term->name));
            if (preg_match('/(^|[^a-z])(plugin|plugins|tema|temas|theme|themes|template|templates)([^a-z]|$)/', $value)) return true;
        }
        return false;
    }

    public static function ensure_table() {
        if (get_option('crapscraper_manual_db_version') === self::DB_VERSION) return;
        global $wpdb;
        require_once ABSPATH . 'wp-admin/includes/upgrade.php';
        $charset = $wpdb->get_charset_collate();
        $table = self::table();
        dbDelta("CREATE TABLE $table (
            id bigint(20) unsigned NOT NULL AUTO_INCREMENT,
            request_id varchar(64) NOT NULL,
            product_id bigint(20) unsigned NOT NULL,
            requested_by bigint(20) unsigned NOT NULL,
            status varchar(32) NOT NULL DEFAULT 'pending',
            job_id varchar(64) NOT NULL DEFAULT '', source varchar(32) NOT NULL DEFAULT '',
            previous_version varchar(64) NOT NULL DEFAULT '', new_version varchar(64) NOT NULL DEFAULT '',
            message text NOT NULL, requested_at datetime NOT NULL, updated_at datetime NOT NULL,
            completed_at datetime NULL,
            PRIMARY KEY (id), UNIQUE KEY request_id (request_id), KEY status (status), KEY product_id (product_id)
        ) $charset;");
        update_option('crapscraper_manual_db_version', self::DB_VERSION, false);
    }

    public static function add_meta_box($post) {
        if (self::authorized() && self::eligible($post->ID))
            add_meta_box('crapscraper-manual-update', 'Atualização CrapScraper', array(__CLASS__, 'render'), 'product', 'side', 'high');
    }

    public static function render($post) { self::render_component($post->ID, 'admin'); }

    public static function render_component($product_id, $context = 'admin') {
        if (!self::authorized() || !self::eligible($product_id)) return;
        $frontend = 'frontend' === $context;
        echo '<aside id="crapscraper-manual" class="cs-manual ' . ($frontend ? 'cs-frontend-panel' : 'cs-admin-panel') . '" data-context="' . esc_attr($context) . '" data-product-id="' . esc_attr($product_id) . '" aria-label="Atualização CrapScraper">';
        if ($frontend) {
            echo '<div class="cs-panel-head" data-cs-drag-handle tabindex="0" role="group" aria-label="Mover painel de atualização; use as setas do teclado">';
            echo '<div><div class="cs-panel-title">Atualização do produto</div><span class="cs-move-hint">Arraste para mover</span></div>';
            echo '<button type="button" class="cs-minimize" data-cs-minimize aria-label="Minimizar painel" aria-expanded="true" title="Minimizar painel"><span aria-hidden="true">−</span></button>';
            echo '</div>';
        }
        echo '<p class="cs-intro">O pedido será processado pelo CrapScraper assim que ele estiver aberto no PC.</p>';
        echo '<button type="button" class="button button-primary" id="crapscraper-manual-button">Verificar e atualizar</button>';
        echo '<div class="cs-loading-space" aria-live="polite">';
        echo '<div id="crapscraper-manual-status" class="cs-status is-idle" role="status">Aguardando verificação.</div>';
        echo '<div id="crapscraper-manual-progress" class="cs-progress" hidden><span></span></div>';
        echo '<dl class="cs-details" id="crapscraper-manual-details">';
        echo '<div><dt>Etapa</dt><dd data-cs-stage>Aguardando ação</dd></div>';
        echo '<div><dt>Origem</dt><dd data-cs-source>—</dd></div>';
        echo '<div><dt>Versão</dt><dd data-cs-version>—</dd></div>';
        echo '</dl></div>';
        echo '<div class="cs-history">';
        echo '<button type="button" class="cs-history-toggle" data-cs-history-toggle aria-expanded="false" aria-controls="crapscraper-manual-history"><span>Últimas 3 atualizações</span><span class="cs-history-chevron" aria-hidden="true">⌄</span></button>';
        echo '<div id="crapscraper-manual-history" class="cs-history-panel" data-cs-history-panel hidden><div class="cs-history-empty">Abra para consultar o histórico.</div></div>';
        echo '</div></aside>';
    }

    private static function frontend_product_id() {
        if (is_admin() || !function_exists('is_product') || !is_product()) return 0;
        return absint(get_queried_object_id());
    }

    private static function enqueue_assets() {
        $base = plugin_dir_url(__FILE__);
        wp_enqueue_script('crapscraper-manual-update', $base . 'manual-update.js', array(), self::DB_VERSION, true);
        wp_enqueue_style('crapscraper-manual-update', $base . 'manual-update.css', array(), self::DB_VERSION);
        wp_localize_script('crapscraper-manual-update', 'CrapScraperManual', array(
            'ajaxUrl' => admin_url('admin-ajax.php'), 'nonce' => wp_create_nonce(self::NONCE_ACTION),
        ));
    }

    public static function assets($hook) {
        global $post;
        if (!self::authorized() || !in_array($hook, array('post.php', 'post-new.php'), true) || !$post || !self::eligible($post->ID)) return;
        self::enqueue_assets();
    }

    public static function frontend_assets() {
        $product_id = self::frontend_product_id();
        if (!$product_id || !self::authorized() || !self::eligible($product_id)) return;
        self::enqueue_assets();
    }

    public static function render_frontend() {
        $product_id = self::frontend_product_id();
        if ($product_id) self::render_component($product_id, 'frontend');
    }

    public static function frontend_no_cache() {
        $product_id = self::frontend_product_id();
        if (!$product_id || !self::authorized() || !self::eligible($product_id)) return;
        nocache_headers();
        if (defined('LSCWP_V')) do_action('litespeed_control_set_nocache', 'CrapScraper Super Admin product control');
    }

    private static function require_admin_request($product_id) {
        check_ajax_referer(self::NONCE_ACTION, 'nonce');
        if (!self::authorized()) wp_send_json_error(array('message' => 'Apenas Super Admin pode executar esta ação.'), 403);
        if (!self::eligible($product_id)) wp_send_json_error(array('message' => 'Produto fora dos tipos Plugin, Tema ou Template.'), 400);
    }

    public static function ajax_start() {
        global $wpdb;
        $product_id = absint(isset($_POST['product_id']) ? $_POST['product_id'] : 0);
        self::require_admin_request($product_id);
        $active = $wpdb->get_row($wpdb->prepare("SELECT * FROM " . self::table() . " WHERE product_id=%d AND status IN ('pending','claimed','locating','comparing','update_found','preparing','processing','executing','validating') ORDER BY id DESC LIMIT 1", $product_id), ARRAY_A);
        if ($active) wp_send_json_success($active);
        $request_id = wp_generate_uuid4(); $now = current_time('mysql', true);
        $wpdb->insert(self::table(), array('request_id'=>$request_id, 'product_id'=>$product_id,
            'requested_by'=>get_current_user_id(), 'status'=>'pending', 'message'=>'Aguardando o CrapScraper no PC.',
            'requested_at'=>$now, 'updated_at'=>$now), array('%s','%d','%d','%s','%s','%s','%s'));
        wp_send_json_success(array('request_id'=>$request_id, 'product_id'=>$product_id, 'status'=>'pending',
            'message'=>'Pedido criado. Abra o CrapScraper no PC para processar.'));
    }

    public static function ajax_status() {
        global $wpdb;
        $product_id = absint(isset($_POST['product_id']) ? $_POST['product_id'] : 0);
        self::require_admin_request($product_id);
        $request_id = sanitize_text_field(isset($_POST['request_id']) ? $_POST['request_id'] : '');
        $row = $wpdb->get_row($wpdb->prepare("SELECT * FROM " . self::table() . " WHERE request_id=%s AND product_id=%d", $request_id, $product_id), ARRAY_A);
        if (!$row) wp_send_json_error(array('message'=>'Pedido não encontrado.'), 404);
        wp_send_json_success($row);
    }

    public static function ajax_history() {
        global $wpdb;
        $product_id = absint(isset($_POST['product_id']) ? $_POST['product_id'] : 0);
        self::require_admin_request($product_id);
        $rows = $wpdb->get_results($wpdb->prepare(
            "SELECT status, source, previous_version, new_version, message, requested_at, updated_at, completed_at FROM " . self::table() . " WHERE product_id=%d ORDER BY id DESC LIMIT 3",
            $product_id
        ), ARRAY_A);
        $history = array();
        foreach ((array) $rows as $row) {
            $raw_date = !empty($row['completed_at']) ? $row['completed_at'] : (!empty($row['updated_at']) ? $row['updated_at'] : $row['requested_at']);
            $local_date = $raw_date ? get_date_from_gmt($raw_date, 'Y-m-d H:i:s') : '';
            $history[] = array(
                'status' => sanitize_key($row['status']),
                'source' => sanitize_text_field($row['source']),
                'previous_version' => sanitize_text_field($row['previous_version']),
                'new_version' => sanitize_text_field($row['new_version']),
                'message' => sanitize_text_field($row['message']),
                'date' => $local_date ? date_i18n('d/m/Y H:i', strtotime($local_date)) : '',
            );
        }
        wp_send_json_success(array('history' => $history));
    }

    private static function rest_secret() {
        return defined('CRAPSCRAPER_MANUAL_SECRET') ? (string) CRAPSCRAPER_MANUAL_SECRET : '';
    }

    public static function rest_permission($request) {
        $secret = self::rest_secret();
        if (strlen($secret) < 24) return new WP_Error('not_configured', 'Segredo da integração não configurado.', array('status'=>503));
        $timestamp = $request->get_header('x-crapscraper-timestamp');
        $nonce = $request->get_header('x-crapscraper-nonce');
        $signature = $request->get_header('x-crapscraper-signature');
        if (!ctype_digit((string)$timestamp) || abs(time()-(int)$timestamp)>300 || !$nonce) return false;
        $nonce_key = 'crapscraper_nonce_' . hash('sha256', $nonce);
        if (get_transient($nonce_key)) return false;
        $subject = $request->get_param('request_id') ?: 'poll';
        $message = implode("\n", array($timestamp, $nonce, $request->get_method(), $request->get_route(), $subject));
        $valid = hash_equals(hash_hmac('sha256', $message, $secret), (string)$signature);
        if ($valid) set_transient($nonce_key, 1, 5 * MINUTE_IN_SECONDS);
        return $valid;
    }

    public static function rest_routes() {
        register_rest_route('crapscraper/v1', '/manual-updates/pending', array('methods'=>'GET',
            'callback'=>array(__CLASS__,'rest_pending'), 'permission_callback'=>array(__CLASS__,'rest_permission')));
        register_rest_route('crapscraper/v1', '/manual-updates/(?P<request_id>[a-zA-Z0-9-]+)/status', array('methods'=>'POST',
            'callback'=>array(__CLASS__,'rest_update_status'), 'permission_callback'=>array(__CLASS__,'rest_permission')));
    }

    private static function no_cache_response($data) {
        nocache_headers();
        if (defined('LSCWP_V')) do_action('litespeed_control_set_nocache', 'CrapScraper manual updates REST');
        $response = rest_ensure_response($data);
        $response->header('Cache-Control', 'no-store, no-cache, must-revalidate, max-age=0');
        $response->header('Pragma', 'no-cache');
        $response->header('Expires', '0');
        $response->header('CDN-Cache-Control', 'no-store');
        $response->header('Cloudflare-CDN-Cache-Control', 'no-store');
        return $response;
    }

    public static function rest_no_cache($served, $result, $request, $server) {
        if (0 === strpos($request->get_route(), '/crapscraper/v1/manual-updates/')) {
            nocache_headers();
            header('Cache-Control: no-store, no-cache, must-revalidate, max-age=0', true);
            header('CDN-Cache-Control: no-store', true);
            if (defined('LSCWP_V')) do_action('litespeed_control_set_nocache', 'CrapScraper manual updates REST');
        }
        return $served;
    }

    public static function rest_pending() {
        global $wpdb; $table=self::table();
        $wpdb->query("UPDATE $table SET status='pending', message='Pedido retomado após expiração da reserva.' WHERE status='claimed' AND updated_at < (UTC_TIMESTAMP() - INTERVAL 10 MINUTE)");
        $rows=$wpdb->get_results("SELECT * FROM $table WHERE status='pending' ORDER BY id ASC LIMIT 10", ARRAY_A);
        foreach ($rows as &$row) {
            $updated=$wpdb->update($table, array('status'=>'claimed','updated_at'=>current_time('mysql',true)),
                array('request_id'=>$row['request_id'],'status'=>'pending'), array('%s','%s'), array('%s','%s'));
            if ($updated) $row['status']='claimed'; else $row=null;
        }
        return self::no_cache_response(array('ok'=>true,'requests'=>array_values(array_filter($rows))));
    }

    public static function rest_update_status($request) {
        global $wpdb; $allowed=array('locating','comparing','update_found','preparing','processing','executing','validating','up_to_date','no_match','source_not_found','source_version_missing','relationship_required','comparison_stale','completed','error','blocked','rolled_back','rollback_required');
        $status=sanitize_key($request->get_param('status'));
        if (!in_array($status,$allowed,true)) return new WP_Error('invalid_status','Status inválido.',array('status'=>400));
        $terminal=in_array($status,array('up_to_date','no_match','source_not_found','source_version_missing','relationship_required','comparison_stale','completed','error','blocked','rolled_back','rollback_required'),true);
        $wpdb->update(self::table(), array('status'=>$status,'job_id'=>sanitize_text_field($request->get_param('job_id')),
            'source'=>sanitize_text_field($request->get_param('source')),'previous_version'=>sanitize_text_field($request->get_param('previous_version')),
            'new_version'=>sanitize_text_field($request->get_param('new_version')),'message'=>sanitize_textarea_field($request->get_param('message')),
            'updated_at'=>current_time('mysql',true),'completed_at'=>$terminal?current_time('mysql',true):null),
            array('request_id'=>$request['request_id']));
        return self::no_cache_response(array('ok'=>true));
    }
}
CrapScraper_Manual_Update::init();
