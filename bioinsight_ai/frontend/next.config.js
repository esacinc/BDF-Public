/** @type {import('next').NextConfig} */
const nextConfig = {
  // Using Next.js server mode (not static export)
  output: "standalone",

  // Prevents Next.js from trying to optimize images (important for Docker/Nginx)
  images: {
    unoptimized: true,
  },

  // Optional: stricter linting can be disabled for smoother builds
  eslint: {
    ignoreDuringBuilds: true,
  },

  // Optional: TypeScript checks can be disabled in Docker
  typescript: {
    ignoreBuildErrors: true,
  },
};

module.exports = nextConfig;
