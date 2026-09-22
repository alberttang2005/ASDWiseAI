export function publicOrigin(request) {
  return new URL(process.env.ASDWISE_PUBLIC_ORIGIN || request.url).origin;
}
