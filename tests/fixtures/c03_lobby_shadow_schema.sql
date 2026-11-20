-- Isolated PostgreSQL 14 shadow fixtures only. No HEL1 or finance DB.
BEGIN;
CREATE ROLE aoe2hd_user NOLOGIN;
CREATE ROLE aoe2war_social_exec_v2 NOLOGIN NOINHERIT;
CREATE ROLE aoe2war_social_writer LOGIN NOINHERIT;
CREATE TABLE public.users (
 id serial PRIMARY KEY,
 uid text UNIQUE NOT NULL,
 verification_method text NOT NULL DEFAULT 'steam',
 in_game_name text,
 steam_persona_name text,
 verification_level integer NOT NULL DEFAULT 1,
 verified boolean NOT NULL DEFAULT true
);
CREATE TABLE public.chat_rooms (
 id serial PRIMARY KEY, slug varchar(80) UNIQUE NOT NULL,
 name varchar(120), scope varchar(20) NOT NULL DEFAULT 'lobby'
);
CREATE TABLE public.chat_messages (
 id serial PRIMARY KEY,
 room_id integer REFERENCES public.chat_rooms(id),
 user_id integer REFERENCES public.users(id),
 body varchar(500),
 created_at timestamp(6) DEFAULT clock_timestamp()
);
CREATE TABLE public.chat_message_guest_reactions (
 id serial PRIMARY KEY,
 message_id integer REFERENCES public.chat_messages(id),
 guest_session_id varchar(64) NOT NULL,
 emoji varchar(24) NOT NULL
);
CREATE TABLE public.chat_message_reactions (
 id serial PRIMARY KEY,
 message_id integer REFERENCES public.chat_messages(id),
 user_id integer REFERENCES public.users(id),
 emoji varchar(24) NOT NULL
);
CREATE SCHEMA aoe2war_social_hd_v2 AUTHORIZATION aoe2hd_user;
REVOKE ALL ON SCHEMA aoe2war_social_hd_v2 FROM PUBLIC;
GRANT USAGE ON SCHEMA aoe2war_social_hd_v2 TO aoe2war_social_writer,aoe2war_social_exec_v2;
CREATE VIEW aoe2war_social_hd_v2.v_users WITH(security_barrier=true) AS
 SELECT id,uid,verification_method,in_game_name,steam_persona_name FROM public.users;
ALTER VIEW aoe2war_social_hd_v2.v_users OWNER TO aoe2hd_user;
GRANT SELECT ON aoe2war_social_hd_v2.v_users TO aoe2war_social_exec_v2;
INSERT INTO public.users(id,uid,verification_method,in_game_name,steam_persona_name,verified)
 VALUES (1,'real-player-a','steam','A','PlayerA',true),
        (2,'real-player-b','steam','B','PlayerB',true),
        (3,'aoe2hd_ai_scribe','system','Scribe','AI',false);
INSERT INTO public.chat_rooms(id,slug,name,scope) VALUES
 (10,'main-lobby','Lobby Chat','lobby'),
 (11,'tournament-private','Private Room','tournament');
INSERT INTO public.chat_messages(id,room_id,user_id,body,created_at) VALUES
 (100,10,1,'Historical lobby record','2026-11-18 12:00:00'),
 (101,11,2,'Private tournament message','2026-11-18 12:01:00');
SELECT setval(pg_get_serial_sequence('public.chat_messages','id'),101,true);
INSERT INTO public.chat_message_guest_reactions(message_id,guest_session_id,emoji)
 VALUES(100,'private-guest-session-id-shall-not-leak','👍');
INSERT INTO public.chat_message_reactions(message_id,user_id,emoji)
 VALUES(100,2,'👍');
ALTER TABLE public.users OWNER TO aoe2hd_user;
ALTER TABLE public.chat_rooms OWNER TO aoe2hd_user;
ALTER TABLE public.chat_messages OWNER TO aoe2hd_user;
ALTER TABLE public.chat_message_guest_reactions OWNER TO aoe2hd_user;
ALTER TABLE public.chat_message_reactions OWNER TO aoe2hd_user;
COMMIT;
