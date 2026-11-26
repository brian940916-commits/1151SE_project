CREATE TABLE IF NOT EXISTS room_profiles (
    room_id bigint PRIMARY KEY REFERENCES rooms(room_id) ON DELETE CASCADE,
    managing_office text,
    key_instructions text,
    equipment text[] NOT NULL DEFAULT '{}',
    cover_url text,
    photo_url text,
    panorama_embed_url text CHECK (panorama_embed_url ~ '^https://' OR panorama_embed_url ~ '^/[^/]'),
    source_url text
);

CREATE TABLE IF NOT EXISTS room_images (
    room_id bigint NOT NULL REFERENCES rooms(room_id) ON DELETE CASCADE,
    kind text NOT NULL CHECK (kind IN ('cover', 'interior')),
    image_data bytea NOT NULL,
    PRIMARY KEY (room_id, kind)
);
