// Made with Claude (Anthropic) · © Homes in Georgia · Created by Irakli Kvirkvelia
'use client';
import { Icon } from './Icon';
import { useFmt } from './Providers';
import { toggleFav, useIsFav } from '@/lib/favorites';
import type { Item } from '@/lib/types';

type Ref = Pick<Item, 'id' | 'legacy_id'>;

/** Heart button. `label` adds the "Save / Saved" text (the listing page); `className` picks the look. */
export default function FavButton({ item, className = 'fav', label = false }: { item: Ref; className?: string; label?: boolean }) {
  const { t } = useFmt();
  const on = useIsFav(item);
  const onClick = (e: React.MouseEvent<HTMLButtonElement>) => {
    e.preventDefault();
    toggleFav(item);
    e.currentTarget.animate([{ transform: 'scale(1)' }, { transform: 'scale(1.25)' }, { transform: 'scale(1)' }], { duration: 260 });
  };
  return (
    <button className={`${className}${on ? ' on' : ''}`} type="button" data-fav={item.id} aria-pressed={on} aria-label={t(on ? 'card.fav.remove' : 'card.fav.add')} onClick={onClick}>
      <Icon name="heart" />{label && <span>{t(on ? 'l.saved' : 'l.save')}</span>}
    </button>
  );
}
