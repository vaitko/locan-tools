// CloudFront Function (viewer-request) for the locan.ai distribution: legacy URL redirects.
// Deployed by scripts/deploy-site.sh (update-function + publish-function on "locan-generator").
// S3 routing rules in infra/s3-website.json are the fallback for requests that bypass CloudFront.
function handler(event) {
  var request = event.request;
  var path = request.uri.replace(/\/+$/, '');

  var redirects = {
    '/GBP-category-optimizer': '/tools/gbp-category-optimizer/',
    '/gbp-category-optimizer': '/tools/gbp-category-optimizer/',
    '/examples': '/guides/',
    '/index-new.html': '/',
    '/index.html.bak2': '/',
    '/index.html.old': '/',
    '/index.html': '/',
  };

  var target = redirects[path];
  if (target) {
    return {
      statusCode: 301,
      statusDescription: 'Moved Permanently',
      headers: {
        location: { value: 'https://locan.ai' + target },
        'cache-control': { value: 'max-age=86400' },
      },
    };
  }

  return request;
}
