--
-- PostgreSQL database dump
--

-- Dumped from database version 9.5.25
-- Dumped by pg_dump version 9.5.25

SET statement_timeout = 0;
SET lock_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

--
-- Name: set_updated_at(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.set_updated_at() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$;


SET default_tablespace = '';

SET default_with_oids = false;

--
-- Name: business_hours; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.business_hours (
    business_hour_id bigint NOT NULL,
    restaurant_id bigint NOT NULL,
    weekday smallint NOT NULL,
    open_time time without time zone,
    close_time time without time zone,
    is_closed boolean DEFAULT false NOT NULL,
    source text,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT business_hours_time_required_ck CHECK ((is_closed OR ((open_time IS NOT NULL) AND (close_time IS NOT NULL)))),
    CONSTRAINT business_hours_weekday_check CHECK (((weekday >= 0) AND (weekday <= 6)))
);


--
-- Name: business_hours_business_hour_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.business_hours_business_hour_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: business_hours_business_hour_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.business_hours_business_hour_id_seq OWNED BY public.business_hours.business_hour_id;


--
-- Name: favorites; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.favorites (
    user_id bigint NOT NULL,
    restaurant_id bigint NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: memberships; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.memberships (
    membership_id bigint NOT NULL,
    user_id bigint NOT NULL,
    trade_no text,
    price numeric(12,2),
    start_date timestamp with time zone DEFAULT now() NOT NULL,
    end_date timestamp with time zone,
    status text DEFAULT 'active'::text NOT NULL,
    payment_provider text,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT memberships_date_order_ck CHECK (((end_date IS NULL) OR (end_date >= start_date))),
    CONSTRAINT memberships_price_check CHECK (((price IS NULL) OR (price >= (0)::numeric)))
);


--
-- Name: memberships_membership_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.memberships_membership_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: memberships_membership_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.memberships_membership_id_seq OWNED BY public.memberships.membership_id;


--
-- Name: payment_transactions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.payment_transactions (
    payment_id bigint NOT NULL,
    membership_id bigint,
    user_id bigint NOT NULL,
    provider text NOT NULL,
    provider_transaction_id text,
    amount numeric(12,2) NOT NULL,
    currency character(3) DEFAULT 'TWD'::bpchar NOT NULL,
    status text NOT NULL,
    paid_at timestamp with time zone,
    raw_payload jsonb,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT payment_transactions_amount_check CHECK ((amount >= (0)::numeric))
);


--
-- Name: payment_transactions_payment_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.payment_transactions_payment_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: payment_transactions_payment_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.payment_transactions_payment_id_seq OWNED BY public.payment_transactions.payment_id;


--
-- Name: photos; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.photos (
    photo_id bigint NOT NULL,
    record_id bigint NOT NULL,
    photo_url text,
    storage_path text,
    sort_order integer DEFAULT 0 NOT NULL,
    uploaded_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT photos_location_required_ck CHECK (((photo_url IS NOT NULL) OR (storage_path IS NOT NULL))),
    CONSTRAINT photos_sort_order_check CHECK ((sort_order >= 0))
);


--
-- Name: photos_photo_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.photos_photo_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: photos_photo_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.photos_photo_id_seq OWNED BY public.photos.photo_id;


--
-- Name: platform_comments; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.platform_comments (
    comment_id bigint NOT NULL,
    record_id bigint NOT NULL,
    user_id bigint NOT NULL,
    text text NOT NULL,
    create_time timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    is_deleted boolean DEFAULT false NOT NULL
);


--
-- Name: platform_comments_comment_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.platform_comments_comment_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: platform_comments_comment_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.platform_comments_comment_id_seq OWNED BY public.platform_comments.comment_id;


--
-- Name: recommendation_items; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.recommendation_items (
    recommendation_item_id bigint NOT NULL,
    recommendation_run_id bigint NOT NULL,
    restaurant_id bigint NOT NULL,
    rank integer NOT NULL,
    score double precision,
    reasons jsonb,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT recommendation_items_rank_check CHECK ((rank > 0))
);


--
-- Name: recommendation_items_recommendation_item_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.recommendation_items_recommendation_item_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: recommendation_items_recommendation_item_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.recommendation_items_recommendation_item_id_seq OWNED BY public.recommendation_items.recommendation_item_id;


--
-- Name: recommendation_runs; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.recommendation_runs (
    recommendation_run_id bigint NOT NULL,
    user_id bigint NOT NULL,
    algorithm_version text NOT NULL,
    request_context jsonb DEFAULT '{}'::jsonb NOT NULL,
    candidate_count integer DEFAULT 0 NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT recommendation_runs_candidate_count_check CHECK ((candidate_count >= 0))
);


--
-- Name: recommendation_runs_recommendation_run_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.recommendation_runs_recommendation_run_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: recommendation_runs_recommendation_run_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.recommendation_runs_recommendation_run_id_seq OWNED BY public.recommendation_runs.recommendation_run_id;


--
-- Name: record_mentions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.record_mentions (
    record_id bigint NOT NULL,
    user_id bigint NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: records; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.records (
    record_id bigint NOT NULL,
    user_id bigint NOT NULL,
    restaurant_id bigint,
    is_public boolean DEFAULT true NOT NULL,
    create_time timestamp with time zone DEFAULT now() NOT NULL,
    text text,
    location_text text,
    location_confidence numeric(5,4),
    value_rating smallint,
    atmosphere_rating smallint,
    taste_rating smallint,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT records_atmosphere_rating_check CHECK (((atmosphere_rating IS NULL) OR ((atmosphere_rating >= 1) AND (atmosphere_rating <= 5)))),
    CONSTRAINT records_location_confidence_check CHECK (((location_confidence IS NULL) OR ((location_confidence >= (0)::numeric) AND (location_confidence <= (1)::numeric)))),
    CONSTRAINT records_taste_rating_check CHECK (((taste_rating IS NULL) OR ((taste_rating >= 1) AND (taste_rating <= 5)))),
    CONSTRAINT records_value_rating_check CHECK (((value_rating IS NULL) OR ((value_rating >= 1) AND (value_rating <= 5))))
);


--
-- Name: records_record_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.records_record_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: records_record_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.records_record_id_seq OWNED BY public.records.record_id;


--
-- Name: restaurant_rows; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.restaurant_rows (
    restaurant_id bigint NOT NULL,
    "googleMaps_id" text NOT NULL,
    title text NOT NULL,
    lng double precision,
    lat double precision,
    "reviewsCount" integer DEFAULT 0 NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    address text,
    website text,
    "categoryName" text,
    phone text,
    topic_avg text,
    CONSTRAINT restaurant_rows_lat_ck CHECK (((lat IS NULL) OR ((lat >= ('-90'::integer)::double precision) AND (lat <= (90)::double precision)))),
    CONSTRAINT restaurant_rows_lng_ck CHECK (((lng IS NULL) OR ((lng >= ('-180'::integer)::double precision) AND (lng <= (180)::double precision)))),
    CONSTRAINT "restaurant_rows_reviewsCount_check" CHECK (("reviewsCount" >= 0))
);


--
-- Name: restaurant_rows_restaurant_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.restaurant_rows_restaurant_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: restaurant_rows_restaurant_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.restaurant_rows_restaurant_id_seq OWNED BY public.restaurant_rows.restaurant_id;


--
-- Name: reviews_rows; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.reviews_rows (
    reviews_id bigint NOT NULL,
    restaurant_id bigint NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    raw_text text NOT NULL,
    cleaned_features text,
    CONSTRAINT reviews_rows_raw_text_not_blank_ck CHECK ((length(btrim(raw_text)) > 0))
);


--
-- Name: reviews_rows_reviews_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.reviews_rows_reviews_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: reviews_rows_reviews_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.reviews_rows_reviews_id_seq OWNED BY public.reviews_rows.reviews_id;


--
-- Name: user_restaurant_events; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.user_restaurant_events (
    event_id bigint NOT NULL,
    user_id bigint NOT NULL,
    restaurant_id bigint NOT NULL,
    recommendation_run_id bigint,
    event_type text NOT NULL,
    rank_at_time integer,
    value double precision,
    metadata jsonb DEFAULT '{}'::jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT user_restaurant_events_rank_at_time_check CHECK (((rank_at_time IS NULL) OR (rank_at_time > 0)))
);


--
-- Name: user_restaurant_events_event_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.user_restaurant_events_event_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: user_restaurant_events_event_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.user_restaurant_events_event_id_seq OWNED BY public.user_restaurant_events.event_id;


--
-- Name: users; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.users (
    user_id bigint NOT NULL,
    user_name text,
    email text,
    password_hash text,
    gender text,
    birthday date,
    phone text,
    registration_date timestamp with time zone DEFAULT now() NOT NULL,
    last_login_at timestamp with time zone,
    role text DEFAULT 'user'::text NOT NULL,
    is_premium boolean DEFAULT false NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: users_user_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.users_user_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: users_user_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.users_user_id_seq OWNED BY public.users.user_id;


--
-- Name: business_hour_id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.business_hours ALTER COLUMN business_hour_id SET DEFAULT nextval('public.business_hours_business_hour_id_seq'::regclass);


--
-- Name: membership_id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.memberships ALTER COLUMN membership_id SET DEFAULT nextval('public.memberships_membership_id_seq'::regclass);


--
-- Name: payment_id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.payment_transactions ALTER COLUMN payment_id SET DEFAULT nextval('public.payment_transactions_payment_id_seq'::regclass);


--
-- Name: photo_id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.photos ALTER COLUMN photo_id SET DEFAULT nextval('public.photos_photo_id_seq'::regclass);


--
-- Name: comment_id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.platform_comments ALTER COLUMN comment_id SET DEFAULT nextval('public.platform_comments_comment_id_seq'::regclass);


--
-- Name: recommendation_item_id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.recommendation_items ALTER COLUMN recommendation_item_id SET DEFAULT nextval('public.recommendation_items_recommendation_item_id_seq'::regclass);


--
-- Name: recommendation_run_id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.recommendation_runs ALTER COLUMN recommendation_run_id SET DEFAULT nextval('public.recommendation_runs_recommendation_run_id_seq'::regclass);


--
-- Name: record_id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.records ALTER COLUMN record_id SET DEFAULT nextval('public.records_record_id_seq'::regclass);


--
-- Name: restaurant_id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.restaurant_rows ALTER COLUMN restaurant_id SET DEFAULT nextval('public.restaurant_rows_restaurant_id_seq'::regclass);


--
-- Name: reviews_id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.reviews_rows ALTER COLUMN reviews_id SET DEFAULT nextval('public.reviews_rows_reviews_id_seq'::regclass);


--
-- Name: event_id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_restaurant_events ALTER COLUMN event_id SET DEFAULT nextval('public.user_restaurant_events_event_id_seq'::regclass);


--
-- Name: user_id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.users ALTER COLUMN user_id SET DEFAULT nextval('public.users_user_id_seq'::regclass);


--
-- Name: business_hours_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.business_hours
    ADD CONSTRAINT business_hours_pkey PRIMARY KEY (business_hour_id);


--
-- Name: favorites_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.favorites
    ADD CONSTRAINT favorites_pkey PRIMARY KEY (user_id, restaurant_id);


--
-- Name: memberships_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.memberships
    ADD CONSTRAINT memberships_pkey PRIMARY KEY (membership_id);


--
-- Name: memberships_trade_no_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.memberships
    ADD CONSTRAINT memberships_trade_no_key UNIQUE (trade_no);


--
-- Name: payment_transactions_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.payment_transactions
    ADD CONSTRAINT payment_transactions_pkey PRIMARY KEY (payment_id);


--
-- Name: payment_transactions_provider_transaction_id_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.payment_transactions
    ADD CONSTRAINT payment_transactions_provider_transaction_id_key UNIQUE (provider_transaction_id);


--
-- Name: photos_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.photos
    ADD CONSTRAINT photos_pkey PRIMARY KEY (photo_id);


--
-- Name: platform_comments_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.platform_comments
    ADD CONSTRAINT platform_comments_pkey PRIMARY KEY (comment_id);


--
-- Name: recommendation_items_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.recommendation_items
    ADD CONSTRAINT recommendation_items_pkey PRIMARY KEY (recommendation_item_id);


--
-- Name: recommendation_items_recommendation_run_id_rank_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.recommendation_items
    ADD CONSTRAINT recommendation_items_recommendation_run_id_rank_key UNIQUE (recommendation_run_id, rank);


--
-- Name: recommendation_items_recommendation_run_id_restaurant_id_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.recommendation_items
    ADD CONSTRAINT recommendation_items_recommendation_run_id_restaurant_id_key UNIQUE (recommendation_run_id, restaurant_id);


--
-- Name: recommendation_runs_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.recommendation_runs
    ADD CONSTRAINT recommendation_runs_pkey PRIMARY KEY (recommendation_run_id);


--
-- Name: record_mentions_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.record_mentions
    ADD CONSTRAINT record_mentions_pkey PRIMARY KEY (record_id, user_id);


--
-- Name: records_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.records
    ADD CONSTRAINT records_pkey PRIMARY KEY (record_id);


--
-- Name: restaurant_rows_googleMaps_id_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.restaurant_rows
    ADD CONSTRAINT "restaurant_rows_googleMaps_id_key" UNIQUE ("googleMaps_id");


--
-- Name: restaurant_rows_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.restaurant_rows
    ADD CONSTRAINT restaurant_rows_pkey PRIMARY KEY (restaurant_id);


--
-- Name: reviews_rows_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.reviews_rows
    ADD CONSTRAINT reviews_rows_pkey PRIMARY KEY (reviews_id);


--
-- Name: user_restaurant_events_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_restaurant_events
    ADD CONSTRAINT user_restaurant_events_pkey PRIMARY KEY (event_id);


--
-- Name: users_email_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_email_key UNIQUE (email);


--
-- Name: users_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_pkey PRIMARY KEY (user_id);


--
-- Name: ix_business_hours_restaurant_weekday; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_business_hours_restaurant_weekday ON public.business_hours USING btree (restaurant_id, weekday);


--
-- Name: ix_favorites_restaurant; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_favorites_restaurant ON public.favorites USING btree (restaurant_id);


--
-- Name: ix_memberships_user_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_memberships_user_status ON public.memberships USING btree (user_id, status);


--
-- Name: ix_payment_transactions_user_created; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_payment_transactions_user_created ON public.payment_transactions USING btree (user_id, created_at);


--
-- Name: ix_photos_record_sort; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_photos_record_sort ON public.photos USING btree (record_id, sort_order);


--
-- Name: ix_platform_comments_record_create_time; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_platform_comments_record_create_time ON public.platform_comments USING btree (record_id, create_time);


--
-- Name: ix_recommendation_items_run_rank; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_recommendation_items_run_rank ON public.recommendation_items USING btree (recommendation_run_id, rank);


--
-- Name: ix_recommendation_runs_algorithm; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_recommendation_runs_algorithm ON public.recommendation_runs USING btree (algorithm_version);


--
-- Name: ix_recommendation_runs_user_created; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_recommendation_runs_user_created ON public.recommendation_runs USING btree (user_id, created_at);


--
-- Name: ix_records_restaurant; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_records_restaurant ON public.records USING btree (restaurant_id);


--
-- Name: ix_records_user_create_time; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_records_user_create_time ON public.records USING btree (user_id, create_time);


--
-- Name: ix_restaurant_rows_lat_lng; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_restaurant_rows_lat_lng ON public.restaurant_rows USING btree (lat, lng);


--
-- Name: ix_reviews_rows_created_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_reviews_rows_created_at ON public.reviews_rows USING btree (created_at);


--
-- Name: ix_reviews_rows_restaurant; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_reviews_rows_restaurant ON public.reviews_rows USING btree (restaurant_id);


--
-- Name: ix_user_restaurant_events_restaurant_created; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_user_restaurant_events_restaurant_created ON public.user_restaurant_events USING btree (restaurant_id, created_at);


--
-- Name: ix_user_restaurant_events_run; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_user_restaurant_events_run ON public.user_restaurant_events USING btree (recommendation_run_id);


--
-- Name: ix_user_restaurant_events_user_created; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_user_restaurant_events_user_created ON public.user_restaurant_events USING btree (user_id, created_at);


--
-- Name: ix_users_role; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_users_role ON public.users USING btree (role);


--
-- Name: business_hours_set_updated_at; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER business_hours_set_updated_at BEFORE UPDATE ON public.business_hours FOR EACH ROW EXECUTE PROCEDURE public.set_updated_at();


--
-- Name: memberships_set_updated_at; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER memberships_set_updated_at BEFORE UPDATE ON public.memberships FOR EACH ROW EXECUTE PROCEDURE public.set_updated_at();


--
-- Name: platform_comments_set_updated_at; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER platform_comments_set_updated_at BEFORE UPDATE ON public.platform_comments FOR EACH ROW EXECUTE PROCEDURE public.set_updated_at();


--
-- Name: records_set_updated_at; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER records_set_updated_at BEFORE UPDATE ON public.records FOR EACH ROW EXECUTE PROCEDURE public.set_updated_at();


--
-- Name: users_set_updated_at; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER users_set_updated_at BEFORE UPDATE ON public.users FOR EACH ROW EXECUTE PROCEDURE public.set_updated_at();


--
-- Name: business_hours_restaurant_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.business_hours
    ADD CONSTRAINT business_hours_restaurant_id_fkey FOREIGN KEY (restaurant_id) REFERENCES public.restaurant_rows(restaurant_id) ON DELETE CASCADE;


--
-- Name: favorites_restaurant_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.favorites
    ADD CONSTRAINT favorites_restaurant_id_fkey FOREIGN KEY (restaurant_id) REFERENCES public.restaurant_rows(restaurant_id) ON DELETE CASCADE;


--
-- Name: favorites_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.favorites
    ADD CONSTRAINT favorites_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(user_id) ON DELETE CASCADE;


--
-- Name: memberships_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.memberships
    ADD CONSTRAINT memberships_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(user_id) ON DELETE CASCADE;


--
-- Name: payment_transactions_membership_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.payment_transactions
    ADD CONSTRAINT payment_transactions_membership_id_fkey FOREIGN KEY (membership_id) REFERENCES public.memberships(membership_id) ON DELETE SET NULL;


--
-- Name: payment_transactions_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.payment_transactions
    ADD CONSTRAINT payment_transactions_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(user_id) ON DELETE CASCADE;


--
-- Name: photos_record_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.photos
    ADD CONSTRAINT photos_record_id_fkey FOREIGN KEY (record_id) REFERENCES public.records(record_id) ON DELETE CASCADE;


--
-- Name: platform_comments_record_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.platform_comments
    ADD CONSTRAINT platform_comments_record_id_fkey FOREIGN KEY (record_id) REFERENCES public.records(record_id) ON DELETE CASCADE;


--
-- Name: platform_comments_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.platform_comments
    ADD CONSTRAINT platform_comments_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(user_id) ON DELETE CASCADE;


--
-- Name: recommendation_items_recommendation_run_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.recommendation_items
    ADD CONSTRAINT recommendation_items_recommendation_run_id_fkey FOREIGN KEY (recommendation_run_id) REFERENCES public.recommendation_runs(recommendation_run_id) ON DELETE CASCADE;


--
-- Name: recommendation_items_restaurant_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.recommendation_items
    ADD CONSTRAINT recommendation_items_restaurant_id_fkey FOREIGN KEY (restaurant_id) REFERENCES public.restaurant_rows(restaurant_id) ON DELETE RESTRICT;


--
-- Name: recommendation_runs_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.recommendation_runs
    ADD CONSTRAINT recommendation_runs_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(user_id) ON DELETE CASCADE;


--
-- Name: record_mentions_record_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.record_mentions
    ADD CONSTRAINT record_mentions_record_id_fkey FOREIGN KEY (record_id) REFERENCES public.records(record_id) ON DELETE CASCADE;


--
-- Name: record_mentions_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.record_mentions
    ADD CONSTRAINT record_mentions_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(user_id) ON DELETE CASCADE;


--
-- Name: records_restaurant_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.records
    ADD CONSTRAINT records_restaurant_id_fkey FOREIGN KEY (restaurant_id) REFERENCES public.restaurant_rows(restaurant_id) ON DELETE SET NULL;


--
-- Name: records_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.records
    ADD CONSTRAINT records_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(user_id) ON DELETE CASCADE;


--
-- Name: reviews_rows_restaurant_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.reviews_rows
    ADD CONSTRAINT reviews_rows_restaurant_id_fkey FOREIGN KEY (restaurant_id) REFERENCES public.restaurant_rows(restaurant_id) ON DELETE CASCADE;


--
-- Name: user_restaurant_events_recommendation_run_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_restaurant_events
    ADD CONSTRAINT user_restaurant_events_recommendation_run_id_fkey FOREIGN KEY (recommendation_run_id) REFERENCES public.recommendation_runs(recommendation_run_id) ON DELETE SET NULL;


--
-- Name: user_restaurant_events_restaurant_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_restaurant_events
    ADD CONSTRAINT user_restaurant_events_restaurant_id_fkey FOREIGN KEY (restaurant_id) REFERENCES public.restaurant_rows(restaurant_id) ON DELETE RESTRICT;


--
-- Name: user_restaurant_events_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_restaurant_events
    ADD CONSTRAINT user_restaurant_events_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(user_id) ON DELETE CASCADE;


--
-- PostgreSQL database dump complete
--

