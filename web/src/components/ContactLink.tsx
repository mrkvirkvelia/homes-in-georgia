// Made with Claude (Anthropic) · © Homes in Georgia · Created by Irakli Kvirkvelia
'use client';
import { usePathname, useRouter } from 'next/navigation';
import { showContact } from '@/lib/contact';

/** Link to the contact block. The full-screen map has no footer, so from there it goes through the home page. */
export default function ContactLink({ className, children }: { className?: string; children: React.ReactNode }) {
  const router = useRouter();
  const onMap = usePathname() === '/map';
  const onClick = (e: React.MouseEvent) => {
    e.preventDefault();
    if (onMap) router.push('/#contact'); // RouteEffects scrolls to the block once the home page is there
    else showContact();
  };
  return <a href="#contact" className={className} data-contact onClick={onClick}>{children}</a>;
}
