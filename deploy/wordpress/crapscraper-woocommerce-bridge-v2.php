<?php
/**
 * Plugin Name: CrapScraper WooCommerce Bridge V2
 * Description: Bridge HMAC com envelope opaco para operações de adição quando o WAF bloqueia /wc/v3.
 * Version: 2.3.0
 */

if (!defined('ABSPATH')) {
    exit;
}

define('CRAPSCRAPER_STORE_BRIDGE_V2_VERSION', '2.3.0');

define('CRAPSCRAPER_STORE_BRIDGE_MAX_COMMAND', 20 * 1024 * 1024);
define('CRAPSCRAPER_STORE_BRIDGE_MAX_IMAGE', 12 * 1024 * 1024);

add_action('rest_api_init', static function (): void {
    register_rest_route('crapscraper/v2', '/bridge', [
        'methods' => 'POST',
        'callback' => 'crapscraper_store_bridge_v2_command',
        'permission_callback' => 'crapscraper_store_bridge_v2_authorize',
    ]);
});

function crapscraper_store_bridge_v2_error_data(int $status): array {
    return [
        'status' => $status,
        'bridge_version' => CRAPSCRAPER_STORE_BRIDGE_V2_VERSION,
    ];
}

function crapscraper_store_bridge_v2_secret(): string {
    if (defined('CRAPSCRAPER_MANUAL_SECRET')) {
        return trim((string) CRAPSCRAPER_MANUAL_SECRET);
    }
    return trim((string) get_option('crapscraper_manual_update_secret', ''));
}

function crapscraper_store_bridge_v2_envelope(WP_REST_Request $request): array {
    $payload = $request->get_json_params();
    if (!is_array($payload)) {
        $payload = [];
    }
    return [
        'timestamp' => trim((string) ($payload['t'] ?? '')),
        'signature' => strtolower(trim((string) ($payload['s'] ?? ''))),
        'encoded' => trim((string) ($payload['p'] ?? '')),
    ];
}

function crapscraper_store_bridge_v2_prime_user(): bool {
    if (get_current_user_id() && current_user_can('manage_woocommerce') && current_user_can('upload_files')) {
        return true;
    }

    $users = get_users([
        'role__in' => ['administrator', 'shop_manager'],
        'number' => 20,
        'orderby' => 'ID',
        'order' => 'ASC',
    ]);
    foreach ($users as $user) {
        if (user_can($user, 'manage_woocommerce') && user_can($user, 'upload_files')) {
            wp_set_current_user((int) $user->ID);
            return true;
        }
    }
    return false;
}

function crapscraper_store_bridge_v2_authorize(WP_REST_Request $request) {
    $secret = crapscraper_store_bridge_v2_secret();
    if (strlen($secret) < 24) {
        return new WP_Error(
            'crapscraper_bridge_secret_missing',
            'Segredo HMAC do CrapScraper não configurado.',
            crapscraper_store_bridge_v2_error_data(503)
        );
    }

    $envelope = crapscraper_store_bridge_v2_envelope($request);
    if ($envelope['timestamp'] === '' || !ctype_digit($envelope['timestamp']) || $envelope['signature'] === '' || $envelope['encoded'] === '') {
        return new WP_Error(
            'crapscraper_bridge_signature_missing',
            'Assinatura CrapScraper ausente.',
            crapscraper_store_bridge_v2_error_data(403)
        );
    }
    if (abs(time() - (int) $envelope['timestamp']) > 300) {
        return new WP_Error(
            'crapscraper_bridge_signature_expired',
            'Assinatura CrapScraper expirada.',
            crapscraper_store_bridge_v2_error_data(403)
        );
    }

    $expected = hash_hmac('sha256', $envelope['timestamp'] . "\n" . $envelope['encoded'], $secret);
    if (!hash_equals($expected, $envelope['signature'])) {
        return new WP_Error(
            'crapscraper_bridge_signature_invalid',
            'Assinatura CrapScraper inválida.',
            crapscraper_store_bridge_v2_error_data(403)
        );
    }

    $decoded = base64_decode($envelope['encoded'], true);
    if ($decoded === false || strlen($decoded) > CRAPSCRAPER_STORE_BRIDGE_MAX_COMMAND) {
        return new WP_Error(
            'crapscraper_bridge_payload_invalid',
            'Envelope CrapScraper inválido ou grande demais.',
            crapscraper_store_bridge_v2_error_data(400)
        );
    }
    $command = json_decode($decoded, true);
    if (!is_array($command)) {
        return new WP_Error(
            'crapscraper_bridge_payload_invalid',
            'Comando CrapScraper inválido.',
            crapscraper_store_bridge_v2_error_data(400)
        );
    }

    if (!crapscraper_store_bridge_v2_prime_user()) {
        return new WP_Error(
            'crapscraper_bridge_operator_missing',
            'Nenhum usuário WordPress com manage_woocommerce e upload_files foi encontrado para executar o bridge.',
            crapscraper_store_bridge_v2_error_data(503)
        );
    }

    $request->set_param('_crapscraper_bridge_command', $command);
    return true;
}

function crapscraper_store_bridge_v2_response($result) {
    if (is_wp_error($result)) {
        $data = $result->get_error_data();
        $status = is_array($data) && !empty($data['status']) ? (int) $data['status'] : 400;
        return new WP_REST_Response([
            'ok' => false,
            'bridge_version' => CRAPSCRAPER_STORE_BRIDGE_V2_VERSION,
            'message' => $result->get_error_message(),
            'code' => $result->get_error_code(),
            'data' => is_array($data) ? $data : [],
        ], $status);
    }

    $response = rest_ensure_response($result);
    $status = method_exists($response, 'get_status') ? (int) $response->get_status() : 200;
    $data = method_exists($response, 'get_data') ? $response->get_data() : $result;
    if ($status >= 400) {
        return new WP_REST_Response([
            'ok' => false,
            'bridge_version' => CRAPSCRAPER_STORE_BRIDGE_V2_VERSION,
            'message' => is_array($data) ? (string) ($data['message'] ?? 'Falha WooCommerce.') : 'Falha WooCommerce.',
            'data' => $data,
        ], $status);
    }
    return new WP_REST_Response([
        'ok' => true,
        'bridge_version' => CRAPSCRAPER_STORE_BRIDGE_V2_VERSION,
        'data' => $data,
    ], 200);
}

function crapscraper_store_bridge_v2_request(string $method, array $params, array $body): WP_REST_Request {
    $request = new WP_REST_Request($method, '/crapscraper-internal');
    if ($params) {
        $request->set_query_params($params);
    }
    if ($body) {
        $request->set_body_params($body);
    }
    return $request;
}

function crapscraper_store_bridge_v2_term_data(WP_Term $term): array {
    return [
        'id' => (int) $term->term_id,
        'name' => (string) $term->name,
        'slug' => (string) $term->slug,
        'parent' => (int) $term->parent,
    ];
}

function crapscraper_store_bridge_v2_taxonomy(string $method, string $path, array $params, array $body) {
    $taxonomy = $path === '/products/categories' ? 'product_cat' : 'product_tag';
    $limit = max(1, min(100, (int) ($params['per_page'] ?? 100)));
    $slug = sanitize_title((string) ($params['slug'] ?? ''));

    if ($method === 'GET') {
        $args = [
            'taxonomy' => $taxonomy,
            'hide_empty' => false,
            'number' => $limit,
        ];
        if ($slug !== '') {
            $args['slug'] = $slug;
        }
        $terms = get_terms($args);
        if (is_wp_error($terms)) {
            return crapscraper_store_bridge_v2_response($terms);
        }
        return new WP_REST_Response([
            'ok' => true,
            'bridge_version' => CRAPSCRAPER_STORE_BRIDGE_V2_VERSION,
            'data' => array_map('crapscraper_store_bridge_v2_term_data', $terms),
        ], 200);
    }

    if ($method !== 'POST') {
        return new WP_REST_Response([
            'ok' => false,
            'bridge_version' => CRAPSCRAPER_STORE_BRIDGE_V2_VERSION,
            'message' => 'Método inválido para taxonomia.',
        ], 405);
    }

    $name = trim((string) ($body['name'] ?? ''));
    if ($name === '') {
        return new WP_REST_Response([
            'ok' => false,
            'bridge_version' => CRAPSCRAPER_STORE_BRIDGE_V2_VERSION,
            'message' => 'Nome da taxonomia vazio.',
        ], 400);
    }
    $wanted_slug = sanitize_title((string) ($body['slug'] ?? $name));

    foreach ([['name' => $name], ['slug' => $wanted_slug]] as $needle) {
        if (reset($needle) === '') {
            continue;
        }
        $existing = get_terms(array_merge([
            'taxonomy' => $taxonomy,
            'hide_empty' => false,
            'number' => 1,
        ], $needle));
        if (!is_wp_error($existing) && $existing) {
            return new WP_REST_Response([
                'ok' => true,
                'bridge_version' => CRAPSCRAPER_STORE_BRIDGE_V2_VERSION,
                'data' => crapscraper_store_bridge_v2_term_data($existing[0]),
            ], 200);
        }
    }

    $parent = $taxonomy === 'product_cat' ? max(0, (int) ($body['parent'] ?? 0)) : 0;
    $created = wp_insert_term($name, $taxonomy, [
        'slug' => $wanted_slug,
        'parent' => $parent,
    ]);
    if (is_wp_error($created)) {
        if ($created->get_error_code() === 'term_exists') {
            $term_id = (int) $created->get_error_data('term_exists');
            $term = $term_id ? get_term($term_id, $taxonomy) : null;
            if ($term instanceof WP_Term) {
                return new WP_REST_Response([
                    'ok' => true,
                    'bridge_version' => CRAPSCRAPER_STORE_BRIDGE_V2_VERSION,
                    'data' => crapscraper_store_bridge_v2_term_data($term),
                ], 200);
            }
        }
        return crapscraper_store_bridge_v2_response($created);
    }

    $term = get_term((int) $created['term_id'], $taxonomy);
    return new WP_REST_Response([
        'ok' => true,
        'bridge_version' => CRAPSCRAPER_STORE_BRIDGE_V2_VERSION,
        'data' => $term instanceof WP_Term ? crapscraper_store_bridge_v2_term_data($term) : ['id' => (int) $created['term_id']],
    ], 200);
}

function crapscraper_store_bridge_v2_media(array $body) {
    $encoded = trim((string) ($body['content_b64'] ?? ''));
    $filename = sanitize_file_name((string) ($body['filename'] ?? 'crapscraper-image.png'));
    $title = sanitize_text_field((string) ($body['title'] ?? pathinfo($filename, PATHINFO_FILENAME)));
    $expected_hash = strtolower(trim((string) ($body['sha256'] ?? '')));

    if ($encoded === '' || $filename === '') {
        return new WP_REST_Response([
            'ok' => false,
            'bridge_version' => CRAPSCRAPER_STORE_BRIDGE_V2_VERSION,
            'message' => 'Imagem validada não foi enviada ao bridge.',
        ], 400);
    }

    $raw = base64_decode($encoded, true);
    if ($raw === false || strlen($raw) <= 1024 || strlen($raw) > CRAPSCRAPER_STORE_BRIDGE_MAX_IMAGE) {
        return new WP_REST_Response([
            'ok' => false,
            'bridge_version' => CRAPSCRAPER_STORE_BRIDGE_V2_VERSION,
            'message' => 'Bytes da imagem são inválidos ou excedem o limite permitido.',
        ], 400);
    }

    $hash = hash('sha256', $raw);
    if ($expected_hash !== '' && !hash_equals($expected_hash, $hash)) {
        return new WP_REST_Response([
            'ok' => false,
            'bridge_version' => CRAPSCRAPER_STORE_BRIDGE_V2_VERSION,
            'message' => 'SHA-256 da imagem divergiu durante o envio ao WordPress.',
        ], 400);
    }

    $info = @getimagesizefromstring($raw);
    $mime = is_array($info) ? strtolower((string) ($info['mime'] ?? '')) : '';
    $allowed = [
        'image/png' => 'png',
        'image/jpeg' => 'jpg',
        'image/webp' => 'webp',
    ];
    if (!isset($allowed[$mime])) {
        return new WP_REST_Response([
            'ok' => false,
            'bridge_version' => CRAPSCRAPER_STORE_BRIDGE_V2_VERSION,
            'message' => 'Imagem recebida pelo bridge não é PNG, JPEG ou WebP válido.',
        ], 400);
    }

    $found = get_posts([
        'post_type' => 'attachment',
        'post_status' => 'inherit',
        'posts_per_page' => 1,
        'fields' => 'ids',
        'meta_key' => 'crapscraper_source_image_sha256',
        'meta_value' => $hash,
    ]);
    if ($found) {
        return new WP_REST_Response([
            'ok' => true,
            'bridge_version' => CRAPSCRAPER_STORE_BRIDGE_V2_VERSION,
            'data' => ['id' => (int) $found[0], 'reused' => true],
        ], 200);
    }

    $uploads = wp_upload_dir();
    if (!empty($uploads['error']) || !wp_mkdir_p($uploads['path'])) {
        return new WP_REST_Response([
            'ok' => false,
            'bridge_version' => CRAPSCRAPER_STORE_BRIDGE_V2_VERSION,
            'message' => 'Pasta de uploads do WordPress não está disponível para o CrapScraper.',
        ], 500);
    }

    $base = sanitize_file_name(pathinfo($filename, PATHINFO_FILENAME));
    $target_name = wp_unique_filename($uploads['path'], ($base !== '' ? $base : 'crapscraper-image') . '.' . $allowed[$mime]);
    $target = trailingslashit($uploads['path']) . $target_name;
    if (@file_put_contents($target, $raw, LOCK_EX) !== strlen($raw)) {
        @unlink($target);
        return new WP_REST_Response([
            'ok' => false,
            'bridge_version' => CRAPSCRAPER_STORE_BRIDGE_V2_VERSION,
            'message' => 'Não foi possível gravar a imagem validada na Biblioteca de Mídia.',
        ], 500);
    }

    $attachment_id = wp_insert_attachment([
        'post_mime_type' => $mime,
        'post_title' => $title !== '' ? $title : $base,
        'post_status' => 'inherit',
    ], $target);
    if (is_wp_error($attachment_id) || !$attachment_id) {
        @unlink($target);
        return crapscraper_store_bridge_v2_response(
            is_wp_error($attachment_id)
                ? $attachment_id
                : new WP_Error('crapscraper_media_insert_failed', 'WordPress não criou o attachment da imagem.', crapscraper_store_bridge_v2_error_data(500))
        );
    }

    require_once ABSPATH . 'wp-admin/includes/image.php';
    $metadata = wp_generate_attachment_metadata((int) $attachment_id, $target);
    if (is_array($metadata)) {
        wp_update_attachment_metadata((int) $attachment_id, $metadata);
    }
    update_post_meta((int) $attachment_id, 'crapscraper_source_image_sha256', $hash);
    update_post_meta((int) $attachment_id, 'crapscraper_source_image_origin', 'bridge_v2_bytes');
    update_post_meta((int) $attachment_id, '_wp_attachment_image_alt', $title);

    return new WP_REST_Response([
        'ok' => true,
        'bridge_version' => CRAPSCRAPER_STORE_BRIDGE_V2_VERSION,
        'data' => ['id' => (int) $attachment_id, 'reused' => false],
    ], 200);
}

function crapscraper_store_bridge_v2_prepare_product_body(array $body) {
    $images = is_array($body['images'] ?? null) ? $body['images'] : [];
    foreach ($images as $image) {
        if (!is_array($image) || empty($image['id'])) {
            return new WP_Error(
                'crapscraper_bridge_product_image_id_required',
                'Produto chegou ao bridge sem um attachment ID validado. Envie a mídia pelo bridge antes de criar o produto.',
                crapscraper_store_bridge_v2_error_data(400)
            );
        }
    }
    return $body;
}

function crapscraper_store_bridge_v2_command(WP_REST_Request $outer) {
    if (!class_exists('WooCommerce')) {
        return new WP_REST_Response([
            'ok' => false,
            'bridge_version' => CRAPSCRAPER_STORE_BRIDGE_V2_VERSION,
            'message' => 'WooCommerce não está ativo.',
        ], 503);
    }

    $payload = $outer->get_param('_crapscraper_bridge_command');
    if (!is_array($payload)) {
        return new WP_REST_Response([
            'ok' => false,
            'bridge_version' => CRAPSCRAPER_STORE_BRIDGE_V2_VERSION,
            'message' => 'Comando CrapScraper ausente.',
        ], 400);
    }

    $method = strtoupper(trim((string) ($payload['method'] ?? '')));
    $path = trim((string) ($payload['path'] ?? ''));
    $params = is_array($payload['params'] ?? null) ? $payload['params'] : [];
    $body = is_array($payload['json'] ?? null) ? $payload['json'] : [];

    if (!in_array($method, ['GET', 'POST', 'PUT'], true)) {
        return new WP_REST_Response([
            'ok' => false,
            'bridge_version' => CRAPSCRAPER_STORE_BRIDGE_V2_VERSION,
            'message' => 'Método não permitido no bridge.',
        ], 405);
    }

    try {
        if ($path === '/media') {
            if ($method !== 'POST') {
                return new WP_REST_Response([
                    'ok' => false,
                    'bridge_version' => CRAPSCRAPER_STORE_BRIDGE_V2_VERSION,
                    'message' => 'Método inválido para mídia.',
                ], 405);
            }
            return crapscraper_store_bridge_v2_media($body);
        }

        if ($path === '/products/categories' || $path === '/products/tags') {
            return crapscraper_store_bridge_v2_taxonomy($method, $path, $params, $body);
        }

        if ($path === '/products') {
            if (!class_exists('WC_REST_Products_Controller')) {
                return new WP_REST_Response([
                    'ok' => false,
                    'bridge_version' => CRAPSCRAPER_STORE_BRIDGE_V2_VERSION,
                    'message' => 'Controller de produtos WooCommerce indisponível.',
                ], 503);
            }
            $controller = new WC_REST_Products_Controller();
            if ($method === 'POST') {
                $body = crapscraper_store_bridge_v2_prepare_product_body($body);
                if (is_wp_error($body)) {
                    return crapscraper_store_bridge_v2_response($body);
                }
            }
            $request = crapscraper_store_bridge_v2_request($method, $params, $body);
            if ($method === 'GET') {
                return crapscraper_store_bridge_v2_response($controller->get_items($request));
            }
            if ($method === 'POST') {
                return crapscraper_store_bridge_v2_response($controller->create_item($request));
            }
            return new WP_REST_Response([
                'ok' => false,
                'bridge_version' => CRAPSCRAPER_STORE_BRIDGE_V2_VERSION,
                'message' => 'Método inválido para produtos.',
            ], 405);
        }

        if (preg_match('~^/products/(\d+)$~', $path, $matches)) {
            if (!class_exists('WC_REST_Products_Controller')) {
                return new WP_REST_Response([
                    'ok' => false,
                    'bridge_version' => CRAPSCRAPER_STORE_BRIDGE_V2_VERSION,
                    'message' => 'Controller de produtos WooCommerce indisponível.',
                ], 503);
            }
            $controller = new WC_REST_Products_Controller();
            $request = crapscraper_store_bridge_v2_request($method, $params, $body);
            $request->set_param('id', (int) $matches[1]);
            if ($method === 'GET') {
                return crapscraper_store_bridge_v2_response($controller->get_item($request));
            }
            if ($method === 'PUT') {
                return crapscraper_store_bridge_v2_response($controller->update_item($request));
            }
            return new WP_REST_Response([
                'ok' => false,
                'bridge_version' => CRAPSCRAPER_STORE_BRIDGE_V2_VERSION,
                'message' => 'Método inválido para produto individual.',
            ], 405);
        }

        if (preg_match('~^/products/(\d+)/variations$~', $path, $matches)) {
            if (!class_exists('WC_REST_Product_Variations_Controller')) {
                return new WP_REST_Response([
                    'ok' => false,
                    'bridge_version' => CRAPSCRAPER_STORE_BRIDGE_V2_VERSION,
                    'message' => 'Controller de variações WooCommerce indisponível.',
                ], 503);
            }
            $controller = new WC_REST_Product_Variations_Controller();
            $request = crapscraper_store_bridge_v2_request($method, $params, $body);
            $request->set_param('product_id', (int) $matches[1]);
            if ($method === 'GET') {
                return crapscraper_store_bridge_v2_response($controller->get_items($request));
            }
            if ($method === 'POST') {
                return crapscraper_store_bridge_v2_response($controller->create_item($request));
            }
            return new WP_REST_Response([
                'ok' => false,
                'bridge_version' => CRAPSCRAPER_STORE_BRIDGE_V2_VERSION,
                'message' => 'Método inválido para variações.',
            ], 405);
        }
    } catch (Throwable $error) {
        return new WP_REST_Response([
            'ok' => false,
            'bridge_version' => CRAPSCRAPER_STORE_BRIDGE_V2_VERSION,
            'message' => 'Falha interna do bridge WooCommerce: ' . $error->getMessage(),
        ], 500);
    }

    return new WP_REST_Response([
        'ok' => false,
        'bridge_version' => CRAPSCRAPER_STORE_BRIDGE_V2_VERSION,
        'message' => 'Caminho não permitido no bridge.',
    ], 404);
}
