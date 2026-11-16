// frontend/middleware.ts
import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";
import { jwtDecode } from "jwt-decode";

type JwtPayload = {
  sub: string;
  role: string;
  exp: number;
};

export function middleware(req: NextRequest) {
  const { pathname } = req.nextUrl;

  // 🚫 Protect both /chat and /chainlit
  if (pathname.startsWith("/chat") || pathname.startsWith("/chainlit")) {
    // Accept token from cookie (preferred) or query param (iframe)
    const token =
      req.cookies.get("token")?.value ||
      req.cookies.get("access_token")?.value ||   
      req.nextUrl.searchParams.get("token");

    if (!token) {
      return NextResponse.redirect(new URL("/login", req.url));
    }

    try {
      const decoded: JwtPayload = jwtDecode(token);

      // Expired?
      if (Date.now() >= decoded.exp * 1000) {
        return NextResponse.redirect(new URL("/login", req.url));
      }

      return NextResponse.next();
    } catch {
      return NextResponse.redirect(new URL("/login", req.url));
    }
  }

  return NextResponse.next();
 }

// Apply middleware to both /chat and /chainlit
export const config = {
  matcher: ["/chat/:path*", "/chainlit/:path*"],
};
