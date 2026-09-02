<?php
/**
 * Plugin Name: CrapScraper Manual Update
 * Description: Fila atualizações seguras de Plugin, Tema e Template para o CrapScraper local.
 * Version: 2.6.0
 */
defined('ABSPATH') || exit;

final class CrapScraper_Manual_Update {
    const NONCE_ACTION = 'crapscraper_manual_update';
    const VERSION = '2.6.0';
    const DB_VERSION = '2.6.0';
    const MONITOR_OPTION = 'crapscraper_manual_monitor_last_seen';
    const MONITOR_ONLINE_SECONDS = 90;
    private static $frontend_rendered = false;

    public static function init() {
        self::ensure_table();
        add_action('add_meta_boxes_product', array(__CLASS__, 'add_meta_box'));
        add_action('admin_enqueue_scripts', array(__CLASS__, 'assets'));
        add_action('wp_enqueue_scripts', array(__CLASS__, 'frontend_assets'));
        add_action('admin_bar_menu', array(__CLASS__, 'admin_bar'), PHP_INT_MAX);
        add_action('wp_footer', array(__CLASS__, 'render_frontend'));
        add_action('template_redirect', array(__CLASS__, 'frontend_no_cache'));
        add_action('wp_ajax_crapscraper_manual_start', array(__CLASS__, 'ajax_start'));
        add_action('wp_ajax_crapscraper_manual_status', array(__CLASS__, 'ajax_status'));
        add_action('wp_ajax_crapscraper_manual_history', array(__CLASS__, 'ajax_history'));
        add_action('wp_ajax_crapscraper_manual_monitor', array(__CLASS__, 'ajax_monitor'));
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
            $candidates = array($term);
            foreach (get_ancestors($term->term_id, 'product_cat', 'taxonomy') as $ancestor_id) {
                $ancestor = get_term($ancestor_id, 'product_cat');
                if ($ancestor && !is_wp_error($ancestor)) $candidates[] = $ancestor;
            }
            foreach ($candidates as $candidate) {
                $value = remove_accents(strtolower($candidate->slug . ' ' . $candidate->name));
                if (preg_match('/(^|[^a-z])(plugin|plugins|tema|temas|theme|themes|template|templates)([^a-z]|$)/', $value)) return true;
            }
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
            operation_id varchar(64) NULL,
            attempt_id varchar(64) NOT NULL DEFAULT '',
            product_id bigint(20) unsigned NOT NULL,
            requested_by bigint(20) unsigned NOT NULL,
            status varchar(32) NOT NULL DEFAULT 'pending',
            stage varchar(32) NOT NULL DEFAULT 'queued',
            job_id varchar(64) NOT NULL DEFAULT '', source varchar(32) NOT NULL DEFAULT '',
            previous_version varchar(64) NOT NULL DEFAULT '', new_version varchar(64) NOT NULL DEFAULT '',
            target_version varchar(64) NOT NULL DEFAULT '',
            message text NOT NULL, requested_at datetime NOT NULL, updated_at datetime NOT NULL,
            completed_at datetime NULL,
            PRIMARY KEY  (id),
            UNIQUE KEY request_id (request_id),
            UNIQUE KEY operation_id (operation_id),
            KEY status (status),
            KEY product_id (product_id)
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
        $toolbar = 'toolbar' === $context;
        echo '<aside id="crapscraper-manual" class="cs-manual ' . ($toolbar ? 'cs-toolbar-panel' : 'cs-admin-panel') . '" data-context="' . esc_attr($context) . '" data-product-id="' . esc_attr($product_id) . '" aria-label="Atualização CrapScraper"' . ($toolbar ? ' role="dialog" style="display:none" hidden' : '') . '>';
        if ($toolbar) {
            $monitor = self::monitor_state();
            echo '<header class="cs-toolbar-head"><div><strong>CrapScraper</strong><span>' . esc_html(get_the_title($product_id)) . '</span></div>';
            echo '<button type="button" class="cs-toolbar-close" data-cs-close aria-label="Fechar janela">&times;</button></header>';
            echo '<section class="cs-accordion">';
            echo '<button type="button" class="cs-accordion-toggle" data-cs-accordion-toggle aria-expanded="true" aria-controls="crapscraper-manual-update-panel"><span class="cs-accordion-label"><span>Atualizar produto</span><span class="cs-monitor is-' . esc_attr($monitor['state']) . '" data-cs-monitor title="' . esc_attr($monitor['title']) . '"><i aria-hidden="true"></i><span data-cs-monitor-label>' . esc_html($monitor['label']) . '</span></span></span><span class="cs-accordion-chevron" aria-hidden="true">▸</span></button>';
            echo '<div id="crapscraper-manual-update-panel" class="cs-accordion-panel" data-cs-accordion-panel>';
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
        if ($toolbar) echo '</div></section>';
        echo '<div class="cs-history">';
        echo '<button type="button" class="cs-history-toggle" data-cs-history-toggle' . ($toolbar ? ' data-cs-accordion-toggle' : '') . ' aria-expanded="false" aria-controls="crapscraper-manual-history"><span>Últimas 3 atualizações</span><span class="cs-history-chevron cs-accordion-chevron" aria-hidden="true">▸</span></button>';
        echo '<div id="crapscraper-manual-history" class="cs-history-panel" data-cs-history-panel hidden><div class="cs-history-empty">Abra para consultar o histórico.</div></div>';
        echo '</div></aside>';
    }

    private static function frontend_product_id() {
        if (is_admin() || !function_exists('is_product') || !is_product()) return 0;
        return absint(get_queried_object_id());
    }

    private static function enqueue_assets() {
        $base = plugin_dir_url(__FILE__);
        wp_enqueue_script('crapscraper-manual-update', $base . 'manual-update.js', array(), self::VERSION, true);
        wp_enqueue_style('crapscraper-manual-update', $base . 'manual-update.css', array(), self::VERSION);
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

    public static function admin_bar($admin_bar) {
        $product_id = self::frontend_product_id();
        if (!$product_id || !is_admin_bar_showing() || !self::authorized() || !self::eligible($product_id)) return;
        $admin_bar->add_node(array(
            'id' => 'crapscraper-manual-toolbar',
            'title' => '<span class="ab-icon" aria-hidden="true"></span><span class="ab-label">CrapScraper</span>',
            'href' => '#crapscraper-manual',
            'meta' => array(
                'class' => 'cs-toolbar-node',
                'title' => 'Atualizar este produto com o CrapScraper',
            ),
        ));
    }

    public static function render_frontend() {
        if (self::$frontend_rendered) return;
        $product_id = self::frontend_product_id();
        if (!$product_id || !is_admin_bar_showing() || !self::authorized() || !self::eligible($product_id)) return;
        self::$frontend_rendered = true;
        self::render_component($product_id, 'toolbar');
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
        $active = $wpdb->get_row($wpdb->prepare("SELECT * FROM " . self::table() . " WHERE product_id=%d AND status IN ('pending','claimed','checking','locating','comparing','update_available','update_found','preparing','processing','executing','validating') ORDER BY id DESC LIMIT 1", $product_id), ARRAY_A);
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
            "SELECT request_id, operation_id, attempt_id, job_id, status, stage, source, previous_version, new_version, target_version, message, requested_at, updated_at, completed_at FROM " . self::table() . " WHERE product_id=%d AND status IN ('completed','already_updated','up_to_date') ORDER BY completed_at DESC, id DESC LIMIT 3",
            $product_id
        ), ARRAY_A);
        $history = array();
        foreach ((array) $rows as $row) {
            $raw_date = !empty($row['completed_at']) ? $row['completed_at'] : (!empty($row['updated_at']) ? $row['updated_at'] : $row['requested_at']);
            $local_date = $raw_date ? get_date_from_gmt($raw_date, 'Y-m-d H:i:s') : '';
            $history[] = array(
                'status' => sanitize_key($row['status']),
                'request_id' => sanitize_text_field($row['request_id']),
                'operation_id' => sanitize_text_field($row['operation_id']),
                'attempt_id' => sanitize_text_field($row['attempt_id']),
                'job_id' => sanitize_text_field($row['job_id']),
                'stage' => sanitize_key($row['stage']),
                'source' => sanitize_text_field($row['source']),
                'previous_version' => sanitize_text_field($row['previous_version']),
                'new_version' => sanitize_text_field($row['new_version']),
                'message' => sanitize_text_field($row['message']),
                'date' => $local_date ? date_i18n('d/m/Y H:i', strtotime($local_date)) : '',
            );
        }
        wp_send_json_success(array('history' => $history));
    }

    private static function touch_monitor() {
        $now = time();
        $last_seen = absint(get_option(self::MONITOR_OPTION, 0));
        if (($now - $last_seen) >= 10) update_option(self::MONITOR_OPTION, $now, false);
    }

    private static function monitor_state() {
        $last_seen = absint(get_option(self::MONITOR_OPTION, 0));
        $age = $last_seen ? max(0, time() - $last_seen) : 0;
        $online = $last_seen && $age <= self::MONITOR_ONLINE_SECONDS;
        return array(
            'state' => $online ? 'online' : 'offline',
            'label' => $online ? 'Online' : 'Offline',
            'title' => $online ? 'Monitor da loja online' : 'Monitor da loja offline',
            'last_seen' => $last_seen,
            'age' => $age,
        );
    }

    public static function ajax_monitor() {
        $product_id = absint(isset($_POST['product_id']) ? $_POST['product_id'] : 0);
        self::require_admin_request($product_id);
        wp_send_json_success(self::monitor_state());
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
        $route = $request->get_route();
        if (false !== strpos($route, '/manual-updates/')) {
            $subject = $request->get_param('request_id') ?: 'poll';
        } else {
            $subject = $request->get_param('operation_id') ?: 'poll';
        }
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
        register_rest_route('crapscraper/v1', '/update-history', array('methods'=>'POST',
            'callback'=>array(__CLASS__,'rest_record_history'), 'permission_callback'=>array(__CLASS__,'rest_permission')));
        register_rest_route('crapscraper/v1', '/update-history/(?P<operation_id>[a-zA-Z0-9-]+)', array('methods'=>'GET',
            'callback'=>array(__CLASS__,'rest_get_history'), 'permission_callback'=>array(__CLASS__,'rest_permission')));
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
        if (0 === strpos($request->get_route(), '/crapscraper/v1/')) {
            nocache_headers();
            header('Cache-Control: no-store, no-cache, must-revalidate, max-age=0', true);
            header('CDN-Cache-Control: no-store', true);
            if (defined('LSCWP_V')) do_action('litespeed_control_set_nocache', 'CrapScraper manual updates REST');
        }
        return $served;
    }

    public static function rest_pending() {
        self::touch_monitor();
        global $wpdb; $table=self::table();
        $wpdb->query("UPDATE $table SET status='pending', stage='queued', message='Pedido retomado após expiração da reserva.', updated_at=UTC_TIMESTAMP() WHERE status IN ('claimed','checking','locating','comparing','update_available','update_found','preparing','processing','executing','validating') AND updated_at < (UTC_TIMESTAMP() - INTERVAL 10 MINUTE)");
        $rows=$wpdb->get_results("SELECT * FROM $table WHERE status='pending' ORDER BY id ASC LIMIT 10", ARRAY_A);
        foreach ($rows as &$row) {
            $updated=$wpdb->update($table, array('status'=>'claimed','updated_at'=>current_time('mysql',true)),
                array('request_id'=>$row['request_id'],'status'=>'pending'), array('%s','%s'), array('%s','%s'));
            if ($updated) $row['status']='claimed'; else $row=null;
        }
        return self::no_cache_response(array('ok'=>true,'requests'=>array_values(array_filter($rows))));
    }

    public static function rest_update_status($request) {
        self::touch_monitor();
        global $wpdb; $allowed=array('checking','locating','comparing','update_available','update_found','preparing','processing','executing','validating','already_updated','up_to_date','no_match','source_not_found','source_version_missing','relationship_required','comparison_stale','completed','error','blocked','rolled_back','rollback_required');
        $status=sanitize_key($request->get_param('status'));
        if (!in_array($status,$allowed,true)) return new WP_Error('invalid_status','Status inválido.',array('status'=>400));
        $terminal=in_array($status,array('already_updated','up_to_date','no_match','source_not_found','source_version_missing','relationship_required','comparison_stale','completed','error','blocked','rolled_back','rollback_required'),true);
        $wpdb->update(self::table(), array('status'=>$status,'stage'=>sanitize_key($request->get_param('stage')),
            'operation_id'=>sanitize_text_field($request->get_param('operation_id')) ?: null,
            'attempt_id'=>sanitize_text_field($request->get_param('attempt_id')),
            'job_id'=>sanitize_text_field($request->get_param('job_id')),
            'source'=>sanitize_text_field($request->get_param('source')),'previous_version'=>sanitize_text_field($request->get_param('previous_version')),
            'new_version'=>sanitize_text_field($request->get_param('new_version')),
            'target_version'=>sanitize_text_field($request->get_param('target_version')),
            'message'=>sanitize_textarea_field($request->get_param('message')),
            'updated_at'=>current_time('mysql',true),'completed_at'=>$terminal?current_time('mysql',true):null),
            array('request_id'=>$request['request_id']));
        return self::no_cache_response(array('ok'=>true));
    }

    private static function history_product_id($raw_product_id) {
        $product_id = absint($raw_product_id);
        if ('product_variation' === get_post_type($product_id)) $product_id = absint(wp_get_post_parent_id($product_id));
        return 'product' === get_post_type($product_id) ? $product_id : 0;
    }

    private static function history_event($row) {
        if (!$row) return null;
        return array(
            'request_id'=>sanitize_text_field($row['request_id']),
            'operation_id'=>sanitize_text_field($row['operation_id'] ?: $row['request_id']),
            'attempt_id'=>sanitize_text_field($row['attempt_id']),
            'job_id'=>sanitize_text_field($row['job_id']),
            'woo_product_id'=>absint($row['product_id']),
            'source'=>sanitize_text_field($row['source']),
            'previous_version'=>sanitize_text_field($row['previous_version']),
            'new_version'=>sanitize_text_field($row['new_version']),
            'target_version'=>sanitize_text_field($row['target_version'] ?: $row['new_version']),
            'state'=>sanitize_key($row['status']),
            'stage'=>sanitize_key($row['stage']),
            'status'=>sanitize_key($row['status']),
            'completed_at'=>sanitize_text_field($row['completed_at']),
        );
    }

    public static function rest_record_history($request) {
        global $wpdb; $table=self::table();
        $operation_id=sanitize_text_field($request->get_param('operation_id'));
        $attempt_id=sanitize_text_field($request->get_param('attempt_id')) ?: $operation_id;
        $job_id=sanitize_text_field($request->get_param('job_id'));
        $product_id=self::history_product_id($request->get_param('woo_product_id'));
        $source=sanitize_text_field($request->get_param('source'));
        $previous=sanitize_text_field($request->get_param('previous_version'));
        $new=sanitize_text_field($request->get_param('new_version'));
        if (!$operation_id || !$job_id || !$product_id || !$source || !$new || 'completed' !== sanitize_key($request->get_param('status')))
            return new WP_Error('invalid_history_event','Evento de atualização incompleto ou inválido.',array('status'=>400));
        $existing=$wpdb->get_row($wpdb->prepare("SELECT * FROM $table WHERE operation_id=%s",$operation_id),ARRAY_A);
        if ($existing) {
            $same=absint($existing['product_id'])===$product_id && $existing['job_id']===$job_id && $existing['source']===$source && $existing['previous_version']===$previous && $existing['new_version']===$new && 'completed'===$existing['status'];
            if (!$same) return new WP_Error('history_conflict','operation_id já existe com dados diferentes.',array('status'=>409));
            return self::no_cache_response(array('ok'=>true,'duplicate'=>true,'event'=>self::history_event($existing)));
        }
        $completed_raw=sanitize_text_field($request->get_param('completed_at'));
        $completed_stamp=$completed_raw ? strtotime($completed_raw) : false;
        $completed_at=$completed_stamp ? gmdate('Y-m-d H:i:s',$completed_stamp) : current_time('mysql',true);
        $manual=$wpdb->get_row($wpdb->prepare("SELECT * FROM $table WHERE product_id=%d AND job_id=%s AND status!='completed' ORDER BY id DESC LIMIT 1",$product_id,$job_id),ARRAY_A);
        $values=array('operation_id'=>$operation_id,'attempt_id'=>$attempt_id,'status'=>'completed','stage'=>'completed','job_id'=>$job_id,'source'=>$source,
            'previous_version'=>$previous,'new_version'=>$new,'target_version'=>$new,'message'=>'Atualização concluída pelo CrapScraper.',
            'updated_at'=>$completed_at,'completed_at'=>$completed_at);
        if ($manual) $saved=$wpdb->update($table,$values,array('id'=>absint($manual['id'])));
        else {
            $values=array_merge($values,array('request_id'=>$operation_id,'product_id'=>$product_id,'requested_by'=>0,'requested_at'=>$completed_at));
            $saved=$wpdb->insert($table,$values);
        }
        if (false === $saved) return new WP_Error('history_not_persisted','Não foi possível persistir o histórico.',array('status'=>500));
        $stored=$wpdb->get_row($wpdb->prepare("SELECT * FROM $table WHERE operation_id=%s",$operation_id),ARRAY_A);
        if (!$stored) return new WP_Error('history_not_confirmed','A gravação não foi confirmada por leitura.',array('status'=>500));
        return self::no_cache_response(array('ok'=>true,'duplicate'=>false,'event'=>self::history_event($stored)));
    }

    public static function rest_get_history($request) {
        global $wpdb;
        $operation_id=sanitize_text_field($request['operation_id']);
        $row=$wpdb->get_row($wpdb->prepare("SELECT * FROM " . self::table() . " WHERE operation_id=%s",$operation_id),ARRAY_A);
        if (!$row) return new WP_Error('history_not_found','Evento de atualização não encontrado.',array('status'=>404));
        return self::no_cache_response(array('ok'=>true,'event'=>self::history_event($row)));
    }
}
CrapScraper_Manual_Update::init();
