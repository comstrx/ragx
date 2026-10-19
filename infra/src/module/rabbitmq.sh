rabbitmq-render () {

    cfg-set RABBITMQ_DEFAULT_USER "${CONFIG[RABBIT_USER]}"
    cfg-set RABBITMQ_DEFAULT_PASS "${CONFIG[RABBIT_PASSWORD]}"

    template-compose-env "${1}/rabbitmq.env" RABBITMQ_DEFAULT_USER RABBITMQ_DEFAULT_PASS

}
