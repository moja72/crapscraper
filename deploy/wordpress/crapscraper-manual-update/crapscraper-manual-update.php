<?php
/**
 * Plugin Name: CrapScraper Manual Update
 * Description: Atualização segura de produtos Plugin, Tema e Template pelo pipeline CrapScraper.
 * Version: 1.0.0
 */

defined('ABSPATH') || exit;

final class CrapScraper_Manual_Update {
    const NONCE_ACTION = 'crapscraper_manual_update';

    public static function init() {
        add_action('add_meta_boxes_product', array(__CLASS__, 'add_meta_box'));
        add_action('admin_enqueue_scripts', array(__CLASS__, 'assets'));
        add_action('wp_ajax_crapscraper_manual_start', array(__CLASS__, 'ajax_start'));
        add_action('wp_ajax_crapscraper_manual_status', array(__CLASS__, 'ajax_status'));
    }

    private static function authorized() {
        return is_user_logged_in() && is_super_admin(get_current_user_id());
    }

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

    public static function add_meta_box($post) {
        if (!self::authorized() || !self::eligible($post->ID)) return;
        add_meta_box('crapscraper-manual-update', 'Atualização CrapScraper', array(__CLASS__, 'render'), 'product', 'side', 'high');
    }

    public static function render($post) {
        wp_nonce_field(self::NONCE_ACTION, 'crapscraper_manual_nonce');
        echo '<div id="crapscraper-manual" data-product-id="' . esc_attr($post->ID) . '">';
        echo '<p>Consulta primeiro o PluginTheme e usa o UltraPackV2 como alternativa.</p>';
        echo '<button type="button" class="button button-primary" id="crapscraper-manual-button">Verificar e atualizar</button>';
        echo '<div id="crapscraper-manual-status" class="cs-status" role="status" aria-live="polite"></div>';
        echo '<div id="crapscraper-manual-progress" class="cs-progress" hidden><span></span></div>';
        echo '</div>';
    }

    public static function assets($hook) {
        global $post;
        if (!self::authorized() || !in_array($hook, array('post.php', 'post-new.php'), true) || !$post || !self::eligible($post->ID)) return;
        $base = plugin_dir_url(__FILE__);
        wp_enqueue_script('crapscraper-manual-update', $base . 'manual-update.js', array(), '1.0.0', true);
        wp_enqueue_style('crapscraper-manual-update', $base . 'manual-update.css', array(), '1.0.0');
        wp_localize_script('crapscraper-manual-update', 'CrapScraperManual', array(
            'ajaxUrl' => admin_url('admin-ajax.php'),
            'nonce' => wp_create_nonce(self::NONCE_ACTION),
        ));
    }

    private static function require_admin_request($product_id) {
        check_ajax_referer(self::NONCE_ACTION, 'nonce');
        if (!self::authorized()) wp_send_json_error(array('message' => 'Apenas Super Admin pode executar esta ação.'), 403);
        if (!self::eligible($product_id)) wp_send_json_error(array('message' => 'Produto fora dos tipos Plugin, Tema ou Template.'), 400);
    }

    private static function api_config() {
        $url = defined('CRAPSCRAPER_MANUAL_API_URL') ? CRAPSCRAPER_MANUAL_API_URL : '';
        $secret = defined('CRAPSCRAPER_MANUAL_SECRET') ? CRAPSCRAPER_MANUAL_SECRET : '';
        if (!$url || strlen($secret) < 24) wp_send_json_error(array('message' => 'Integração CrapScraper não configurada.'), 500);
        return array(rtrim($url, '/'), $secret);
    }

    private static function signed_request($method, $path, $subject, $body = null) {
        list($base, $secret) = self::api_config();
        $timestamp = (string) time();
        $nonce = wp_generate_uuid4();
        $signed_path = strtok($path, '?');
        $message = implode("\n", array($timestamp, $nonce, strtoupper($method), $signed_path, (string) $subject));
        $args = array('method' => $method, 'timeout' => 30, 'headers' => array(
            'Accept' => 'application/json', 'Content-Type' => 'application/json',
            'X-CrapScraper-Timestamp' => $timestamp, 'X-CrapScraper-Nonce' => $nonce,
            'X-CrapScraper-Signature' => hash_hmac('sha256', $message, $secret),
        ));
        if (null !== $body) $args['body'] = wp_json_encode($body);
        $response = wp_remote_request($base . $path, $args);
        if (is_wp_error($response)) wp_send_json_error(array('message' => $response->get_error_message()), 502);
        $payload = json_decode(wp_remote_retrieve_body($response), true);
        if (wp_remote_retrieve_response_code($response) >= 400 || empty($payload['ok'])) {
            wp_send_json_error(array('message' => isset($payload['message']) ? $payload['message'] : 'Falha no CrapScraper.'), wp_remote_retrieve_response_code($response) ?: 502);
        }
        return $payload;
    }

    public static function ajax_start() {
        $product_id = absint(isset($_POST['product_id']) ? $_POST['product_id'] : 0);
        self::require_admin_request($product_id);
        $user = wp_get_current_user();
        $payload = self::signed_request('POST', '/wordpress/manual-update', $product_id, array(
            'product_id' => $product_id, 'initiated_by' => $user->user_login . ' (#' . $user->ID . ')',
        ));
        wp_send_json_success($payload);
    }

    public static function ajax_status() {
        $product_id = absint(isset($_POST['product_id']) ? $_POST['product_id'] : 0);
        self::require_admin_request($product_id);
        $job_id = sanitize_text_field(isset($_POST['job_id']) ? $_POST['job_id'] : '');
        if (!$job_id) wp_send_json_error(array('message' => 'Job inválido.'), 400);
        wp_send_json_success(self::signed_request('GET', '/wordpress/manual-update/status?job_id=' . rawurlencode($job_id), $job_id));
    }
}

CrapScraper_Manual_Update::init();
