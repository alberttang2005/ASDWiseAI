export default {
  devIndicators: false,
  async rewrites() {
    return process.env.VERCEL ? [] : {beforeFiles:[{source:'/api/index',destination:'http://127.0.0.1:8001/api/index'}]};
  }
};
