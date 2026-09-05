<?php
/**
 * Plugin Name: CrapScraper WooCommerce Variation Bridge
 * Description: Extensão HMAC mínima para corrigir variações existentes quando o WAF bloqueia PUT em /wc/v3.
 * Version: 1.0.0
 */

if (!defined('ABSPATH')) {
    exit;
}

define('CRAPSCRAPER_VARIATION_BRIDGE_VERSION', '1.0.0');

add_action('rest_api_init', static function (): void {
    register_rest_route('crapscraper/v2', '/variation-update', [
        'methods' => 'POST',
        'callback' => 'crapscraper_variation_bridge_command',
        'permission_callback' => 'crapscraper_variation_bridge_authorize',
    ]);
});

function crapscraper_variation_bridge_secret(): string {
    if (defined('CRAPSCRAPER_MANUAL_SECRET')) {
        return trim((string) CRAPSCRAPER_MANUAL_SECRET);
    }
    return trim((string) get_option('crapscraper_manual_update_secret', ''));
}

function crapscraper_variation_bridge_error(string $code, string $message, int $status) {
    return new WP_Error($code, $message, [
        'status' => $status,
        'bridge_version' => CRAPSCRAPER_VARIATION_BRIDGE_VERSION,
    ]);
}

function crapscraper_variation_bridge_prime_user(): bool {
    if (get_current_user_id() && current_user_can('manage_woocommerce')) {
        return true;
    }
    $users = get_users([
        'role__in' => ['administrator', 'shop_manager'],
        'number' => 20,
        'orderby' => 'ID',
        'order' => 'ASC',
    ]);
    foreach ($users as $user) {
        if (user_can($user, 'manage_woocommerce')) {
            wp_set_current_user((int) $user->ID);
            return true;
        }
    }
    return false;
}

function crapscraper_variation_bridge_authorize(WP_REST_Request $request) {
    $secret = crapscraper_variation_bridge_secret();
    if (strlen($secret) < 24) {
        return crapscraper_variation_bridge_error('crapscraper_variation_secret_missing', 'Segredo HMAC do CrapScraper não configurado.', 503);
    }

    $envelope = $request->get_json_params();
    if (!is_array($envelope)) {
        $envelope = [];
    }
    $timestamp = trim((string) ($envelope['t'] ?? ''));
    $signature = strtolower(trim((string) ($envelope['s'] ?? '')));
    $encoded = trim((string) ($envelope['p'] ?? ''));
    if ($timestamp === '' || !ctype_digit($timestamp) || $signature === '' || $encoded === '') {
        return crapscraper_variation_bridge_error('crapscraper_variation_signature_missing', 'Assinatura CrapScraper ausente.', 403);
    }
    if (abs(time() - (int) $timestamp) > 300) {
        return crapscraper_variation_bridge_error('crapscraper_variation_signature_expired', 'Assinatura CrapScraper expirada.', 403);
    }
    $expected = hash_hmac('sha256', $timestamp . "\n" . $encoded, $secret);
    if (!hash_equals($expected, $signature)) {
        return crapscraper_variation_bridge_error('crapscraper_variation_signature_invalid', 'Assinatura CrapScraper inválida.', 403);
    }

    $decoded = base64_decode($encoded, true);
    $command = $decoded !== false ? json_decode($decoded, true) : null;
    if (!is_array($command)) {
        return crapscraper_variation_bridge_error('crapscraper_variation_payload_invalid', 'Comando CrapScraper inválido.', 400);
    }
    if (strtoupper((string) ($command['method'] ?? '')) !== 'PUT') {
        return crapscraper_variation_bridge_error('crapscraper_variation_method_invalid', 'Somente PUT de variação é permitido.', 405);
    }
    $path = trim((string) ($command['path'] ?? ''));
    if (!preg_match('~^/products/(\d+)/variations/(\d+)$~', $path, $matches)) {
        return crapscraper_variation_bridge_error('crapscraper_variation_path_invalid', 'Caminho de variação não permitido.', 404);
    }
    if (!crapscraper_variation_bridge_prime_user()) {
        return crapscraper_variation_bridge_error('crapscraper_variation_operator_missing', 'Nenhum operador WooCommerce disponível.', 503);
    }

    $request->set_param('_crapscraper_variation_command', $command);
    $request->set_param('_crapscraper_product_id', (int) $matches[1]);
    $request->set_param('_crapscraper_variation_id', (int) $matches[2]);
    return true;
}

function crapscraper_variation_bridge_command(WP_REST_Request $outer) {
    if (!class_exists('WooCommerce') || !class_exists('WC_REST_Product_Variations_Controller')) {
        return new WP_REST_Response([
            'ok' => false,
            'bridge_version' => CRAPSCRAPER_VARIATION_BRIDGE_VERSION,
            'message' => 'Controller de variações WooCommerce indisponível.',
        ], 503);
    }

    $command = $outer->get_param('_crapscraper_variation_command');
    $product_id = (int) $outer->get_param('_crapscraper_product_id');
    $variation_id = (int) $outer->get_param('_crapscraper_variation_id');
    $body = is_array($command['json'] ?? null) ? $command['json'] : [];

    $variation = wc_get_product($variation_id);
    if (!$variation || !$variation->is_type('variation') || (int) $variation->get_parent_id() !== $product_id) {
        return new WP_REST_Response([
            'ok' => false,
            'bridge_version' => CRAPSCRAPER_VARIATION_BRIDGE_VERSION,
            'message' => 'Variação não pertence ao produto informado.',
        ], 404);
    }

    try {
        $controller = new WC_REST_Product_Variations_Controller();
        $request = new WP_REST_Request('PUT', '/crapscraper-internal');
        $request->set_body_params($body);
        $request->set_param('product_id', $product_id);
        $request->set_param('id', $variation_id);
        $result = $controller->update_item($request);
        if (is_wp_error($result)) {
            return new WP_REST_Response([
                'ok' => false,
                'bridge_version' => CRAPSCRAPER_VARIATION_BRIDGE_VERSION,
                'message' => $result->get_error_message(),
                'code' => $result->get_error_code(),
            ], 400);
        }
        $response = rest_ensure_response($result);
        $status = method_exists($response, 'get_status') ? (int) $response->get_status() : 200;
        $data = method_exists($response, 'get_data') ? $response->get_data() : $result;
        if ($status >= 400) {
            return new WP_REST_Response([
                'ok' => false,
                'bridge_version' => CRAPSCRAPER_VARIATION_BRIDGE_VERSION,
                'message' => is_array($data) ? (string) ($data['message'] ?? 'Falha ao atualizar variação.') : 'Falha ao atualizar variação.',
                'data' => $data,
            ], $status);
        }
        return new WP_REST_Response([
            'ok' => true,
            'bridge_version' => CRAPSCRAPER_VARIATION_BRIDGE_VERSION,
            'data' => $data,
        ], 200);
    } catch (Throwable $error) {
        return new WP_REST_Response([
            'ok' => false,
            'bridge_version' => CRAPSCRAPER_VARIATION_BRIDGE_VERSION,
            'message' => 'Falha interna ao atualizar variação: ' . $error->getMessage(),
        ], 500);
    }
}
