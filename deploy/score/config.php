<?php
// Deployment settings contain no passwords. Secrets and the database live outside the web root.
return [
    'origin' => 'https://mecharena.eu',
    'base_url' => 'https://mecharena.eu/score',
    'data_dir' => dirname(__DIR__, 2) . '/.mecharena-score',
    'admins' => ['kaur@mecharena.eu'],
    'from' => 'kaur@mecharena.eu',
    'session_seconds' => 604800,
];
