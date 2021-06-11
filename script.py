__author__ = "Stefano Bonato"
__copyright__ = "Copyright 2021"
__credits__ = ["Stefano Bonato"]
__license__ = "GPL"
__version__ = "1.0.0"
__maintainer__ = "Stefano Bonato"
__email__ = "bonato.ste@gmail.com"
__status__ = "Production"

import random
from functools import partial
from datetime import datetime as dt
from time import sleep

import yaml
from selenium import webdriver
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.wait import WebDriverWait


def priorita_sede(sede: WebElement, settaggi: dict) -> int:
    """
    Restituisce la priorità della sede se questa contiene nel nome una delle sottostringhe specificate in "priorita_sedi"
    Altrimenti restituisce la priorità più bassa possibile
    """
    for k, v in settaggi['priorita_sedi'].items():
        if k in sede.text:
            return v
    return len(settaggi['priorita_sedi'])


def attendi_elemento(pattern, by, mode='present', wait=5, error=True):
    """ Cerca il nodo con il pattern specificato. Passati alcuni secondi (wait=5) dà un TimeoutException.
    Se error=False, in tal caso restituisce None invece di bloccare l'esecuzione del programma """

    ecs = {'present': EC.presence_of_element_located,
           'visible': EC.visibility_of_element_located,
           'clickable': EC.element_to_be_clickable}

    try:
        sleep(0.1)
        browser.implicitly_wait(2)
        rst = WebDriverWait(browser, wait).until(ecs[mode]((by, pattern)))
        browser.implicitly_wait(2)
        sleep(0.1)
        return rst
    except TimeoutException as ex:
        if error:
            raise ex
        else:
            return None


# Carico in memoria i dati specificati dal'utente
with open('config.yaml', 'r') as stream:
    settaggi = yaml.safe_load(stream)
settaggi['priorita_sedi'] = {s: i for i, s in enumerate(settaggi['priorita_sedi'])}

# Apro il browser e carico la pagina ulss specificata dall'utente
browser = webdriver.Firefox()
print(f'Carico la piattaforma ulss{settaggi["ulss"]}')
browser.get(f'https://vaccinicovid.regione.veneto.it/ulss{settaggi["ulss"]}')

print(f'Prenotazione automatica vaccino per: {settaggi["nome"]}')
sedi_ord_pref = [k for k, v in sorted(settaggi["priorita_sedi"].items(), key=lambda x: x[1])]
print(f'Sedi preferite (in ordine): {", ".join(sedi_ord_pref)}')
data_minima = dt.strptime(settaggi['data_minima'], '%Y-%m-%d')
data_limite = dt.strptime(settaggi['data_limite'], '%Y-%m-%d')

print(f'Intervallo di date accettabili: {settaggi["data_minima"]} - {settaggi["data_limite"]}')

while True:
    # Aspetta per un periodo variabile, per diminuire le chance di ricevere una chiamata da sti campioni
    attesa = settaggi['tempo_attesa'] + random.random() * settaggi['tempo_attesa']
    print(f'Aspetto {attesa:2.2f} secondi')
    sleep(attesa)

    # A volte non trova tutti i campi nello stesso istante quindi in questo modo riprova finché non li trova tutti
    print('Inserisco e confermo le credenziali di login')
    while True:
        input_cod_fiscale = attendi_elemento('cod_fiscale', By.NAME, 'visible', error=False)
        input_num_tessera = attendi_elemento('num_tessera', By.NAME, 'visible', error=False)
        checkbox_consenso = attendi_elemento("(//input[@type='checkbox'])[last()]", By.XPATH, 'visible',
                                             error=False)

        if all([x is not None for x in [input_cod_fiscale, input_num_tessera, checkbox_consenso]]):
            break
        else:
            browser.refresh()
            continue

    # Compila i campi della prima schermata
    input_cod_fiscale.send_keys(settaggi['cod_fiscale'])
    input_num_tessera.send_keys(settaggi['num_tessera'])
    checkbox_consenso.click()

    # Conferma i campi appena compilati
    attendi_elemento('//button[normalize-space()="Conferma"]', By.XPATH, 'clickable').click()

    # Da poco c'è questo passaggio intermedio ulteriore
    print('Seleziono il servizio per giovani')
    attendi_elemento('//button[normalize-space()="Nati dal 1962 al 2009"]', By.XPATH, 'clickable').click()

    # Aspetto che ci sia scritto "Selezionare una sede" e poi leggo tutti i button dopo questa scritta
    attendi_elemento('//h2[normalize-space()="Selezionare una sede"]', By.XPATH, 'visible')
    sedi = browser.find_elements_by_xpath('//h2[normalize-space()="Selezionare una sede"]/following-sibling::button')

    # Tengo traccia solamente di quelli attivi
    sedi = [p for ip, p in enumerate(sedi) if p.get_attribute('onclick') is not None]

    # Li ordino secondo la priorità specificata dall'utente
    sedi = sorted(sedi, key=partial(priorita_sede, settaggi=settaggi))

    # Se la whitelist contiene almeno un valore, tieni solo le sedi che contengono i valori della whitelist
    sedi = list(filter(lambda s: all([x not in s.text for x in settaggi['blacklist']]), sedi))

    # Se non ci sono sedi disponibili provo a tornare indietro con i tasti invece che refreshare
    # TODO: Sembrerebbe più veloce, forse è il caso di testare
    if len(sedi) == 0:
        torna_indietro = attendi_elemento('//button[normalize-space()="Torna a scelta servizio"]', By.XPATH,
                                          'clickable', error=False)
        if torna_indietro is not None:
            torna_indietro.click()
        else:
            browser.refresh()
            continue
        torna_indietro = attendi_elemento('//button[normalize-space()="Torna a identificazione"]', By.XPATH,
                                          'clickable', error=False)
        if torna_indietro is not None:
            torna_indietro.click()
        else:
            browser.refresh()
        continue

    # Seleziona la prima sede della lista (a questo punto è già in ordine di priorità)
    pretty_sedi_disp = [s.text.strip()[:16] for s in sedi]
    s = sedi[0].text
    print(f'Sede selezionata: {s} (disponibili: {", ".join(pretty_sedi_disp)})')
    sedi[0].click()

    # Cerca di mese in mese se c'è qualcosa
    date_disp = []
    while True:
        # Calendario visibile?
        attendi_elemento("td.fc-day-other", By.CSS_SELECTOR, 'visible')
        # Allora cerca date disponibili

        giorni_mese = sorted(browser.find_elements_by_css_selector("td.fc-daygrid-day:not(.fc-day-other)"),
                             key=lambda x: int(x.text))
        date_disp = [day_element for day_element in giorni_mese if 'highlight' in day_element.get_attribute('class')]
        print("Date disponibili (senza filtri):", ", ".join([g.get_attribute('data-date') for g in date_disp]))
        date_disp = [g for g in date_disp
                     if data_minima <= dt.strptime(g.get_attribute('data-date'), '%Y-%m-%d') <= data_limite]

        if len(date_disp) == 0:
            if dt.strptime(giorni_mese[-1].get_attribute('data-date'), '%Y-%m-%d') >= data_limite:
                break

            # Vai al prossimo mese
            attendi_elemento('button.fc-next-button', By.CSS_SELECTOR, 'clickable').click()
        else:
            prima_data_disp = dt.strptime(date_disp[0].get_attribute('data-date'), '%Y-%m-%d')
            if prima_data_disp > data_limite:
                print(f'Scarto {date_disp[0].get_attribute("data-date")} perché è troppo tardi')
                date_disp = []
            break

    # Da qui in poi è più facile refreshare che tornare indietro manualmente, nel caso qualcosa vada storto
    if len(date_disp) == 0:
        browser.refresh()
        continue

    # Seleziona la prima data disponibile trovata
    pretty_date_disp = [d.get_attribute("data-date") for d in date_disp]
    print(f'Data selezionata: {date_disp[0].get_attribute("data-date")} (disponibili: {", ".join(pretty_date_disp)})')
    date_disp[0].click()

    # A questo punto potrebbe essere già stata presa da qualcuno col dito veloce, controlla che sia tutto ok
    # alert_goback = attendi_elemento("div.alert.alert-danger", By.CSS_SELECTOR, 'visible', wait=1, error=False)
    # if alert_goback is not None:
    #     browser.refresh()
    #     continue

    # Aspetto che ci sia scritto "Fasce disponibili.." e poi leggo tutti i button dopo questa scritta
    attendi_elemento("//h2[text()[contains(.,'Fasce disponibili')]]/following-sibling::button", By.XPATH,
                     'clickable', wait=3)
    hours = browser.find_elements_by_xpath(
        "//h2[text()[contains(.,'Fasce disponibili')]]/following-sibling::button")
    if len(hours) == 0:
        browser.refresh()
        continue

    # Se si liberano tot ore forse è il caso di non andare alle prime, che proveranno tutti gli altri
    # random.shuffle(hours)

    # Seleziona la prima slot oraria della lista
    print(f'Seleziono slot oraria: {hours[0].text}')
    hours[0].click()

    # Stesso discorso dei campi della prima schermata
    print('Inserisco le credenziali finali')
    while True:
        input_cognome = attendi_elemento('cognome', By.NAME, 'visible', error=False)
        input_nome = attendi_elemento('nome', By.NAME, 'visible', error=False)
        input_email = attendi_elemento('email', By.NAME, 'visible', error=False)
        input_cellulare = attendi_elemento('cellulare', By.NAME, 'visible', error=False)

        if all([x is not None for x in [input_cognome, input_nome, input_email, input_cellulare]]):
            break
        else:
            browser.refresh()
            continue

    input_cognome.send_keys(settaggi['cognome'])
    input_nome.send_keys(settaggi['nome'])
    input_email.send_keys(settaggi['email'])
    input_cellulare.send_keys(settaggi['cellulare'])

    # Conferma finale che effettua la prenotazione
    attendi_elemento('//button[normalize-space()="Conferma"]', By.XPATH, 'clickable').click()

    # Controllo che sia stato prenotato con successo
    popup_classes = attendi_elemento('swal2-popup', By.CLASS_NAME, 'visible').get_attribute('class')
    if 'error' in popup_classes:
        print('C\'è stato qualcuno più veloce di me, prenotazione fallita')
        browser.refresh()
        continue
    else:
        print('Vaccino prenotato con successo')
        input()
