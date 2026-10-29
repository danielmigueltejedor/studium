CREATE TABLE `library_versions` (
	`user_id` text NOT NULL,
	`revision` integer NOT NULL,
	`object_key` text NOT NULL,
	`updated` integer NOT NULL,
	PRIMARY KEY(`user_id`, `revision`)
);
--> statement-breakpoint
CREATE TABLE `oauth_states` (
	`state_hash` text PRIMARY KEY NOT NULL,
	`user_id` text NOT NULL,
	`provider` text NOT NULL,
	`session_hash` text NOT NULL,
	`ciphertext` text NOT NULL,
	`expires` integer NOT NULL
);
